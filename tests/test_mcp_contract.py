import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from excalidraw_mcp.service import SceneService
from fastmcp import Client
from excalidraw_mcp.server import create_server


class MCPContractTests(unittest.TestCase):
    @staticmethod
    def metadata(server):
        return {tool.name: tool for tool in asyncio.run(server.list_tools())}

    def test_tools_have_constraints_outputs_and_behavior_annotations(self):
        tools = self.metadata(create_server(toolset="full"))
        structured = set(tools) - {"export_scene", "preview", "get_canvas_screenshot"}
        self.assertTrue(all(tools[name].output_schema for name in structured))
        width = tools["add_rectangle"].parameters["properties"]["w"]
        self.assertEqual((width["exclusiveMinimum"], width["maximum"]), (0, 100000))
        self.assertEqual(
            tools["add_rectangle"].parameters["properties"]["fillStyle"]["anyOf"][0][
                "enum"
            ],
            ["solid", "hachure", "cross-hatch", "zigzag"],
        )
        self.assertTrue(tools["get_scene"].annotations.readOnlyHint)
        self.assertFalse(tools["get_scene"].annotations.openWorldHint)
        self.assertTrue(tools["clear"].annotations.destructiveHint)
        self.assertTrue(tools["save"].annotations.openWorldHint)
        self.assertTrue(tools["draw_graph"].annotations.destructiveHint)
        self.assertTrue(all(not tool.run_in_thread for tool in tools.values()))

    def test_graph_schema_rejects_unknown_fields_and_has_enums(self):
        schema = self.metadata(create_server(toolset="full"))["draw_graph"].parameters
        node_definition = schema["properties"]["nodes"]["items"]
        self.assertFalse(node_definition["additionalProperties"])
        self.assertEqual(
            node_definition["properties"]["shape"]["enum"],
            ["rectangle", "ellipse", "diamond"],
        )
        self.assertEqual(
            schema["properties"]["layout"]["enum"],
            ["layered", "horizontal", "vertical"],
        )

    def test_missing_targets_are_tool_errors_at_adapter_boundary(self):
        tools = {
            tool.name: tool.fn for tool in asyncio.run(create_server().list_tools())
        }
        from fastmcp.exceptions import ToolError

        with self.assertRaises(ToolError):
            tools["get_element"]("missing")
        with self.assertRaises(ToolError):
            tools["delete"]("missing")

    def test_saved_scene_resource_template_reads_without_loading(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": directory}),
        ):
            service = SceneService()
            service.add_text(0, 0, "saved")
            service.save("example")
            service.clear()
            server = create_server(service)
            templates = asyncio.run(server.list_resource_templates())
            self.assertEqual(
                [str(item.uri_template) for item in templates],
                ["excalidraw://scenes/{name}.excalidraw"],
            )
            provider = templates[0]
            result = asyncio.run(provider.read({"name": "example"}))
            text = (
                result
                if isinstance(result, str)
                else (result.content if hasattr(result, "content") else result.text)
            )
            self.assertEqual(json.loads(text)["elements"][0]["text"], "saved")
            self.assertEqual(service.state.all(), [])


class MCPExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_calls_return_structured_success_and_errors(self):
        async with Client(create_server(toolset="full"), timeout=5) as client:
            created = await client.call_tool(
                "add_rectangle",
                {
                    "x": 0,
                    "y": 0,
                    "w": 100,
                    "h": 80,
                    "label": "API",
                },
            )
            inspected = await client.call_tool("get_scene", {})
            invalid = await client.call_tool(
                "add_rectangle",
                {
                    "x": 0,
                    "y": 0,
                    "w": -1,
                    "h": 80,
                },
                raise_on_error=False,
            )
            missing = await client.call_tool(
                "delete",
                {
                    "element_id": "missing",
                },
                raise_on_error=False,
            )
            graph = await client.call_tool(
                "draw_graph",
                {
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"id": "a-to-b", "source": "a", "target": "b"}],
                },
            )
        self.assertFalse(created.is_error)
        self.assertEqual(inspected.structured_content["total"], 2)
        self.assertTrue(invalid.is_error)
        self.assertTrue(missing.is_error)
        self.assertEqual(graph.structured_content["node_map"].keys(), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
