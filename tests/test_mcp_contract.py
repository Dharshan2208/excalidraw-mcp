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
        # Output schemas stripped from tools/list to reduce client schema footprint
        self.assertTrue(all(tool.output_schema is None for tool in tools.values()))
        width = tools["create_shape"].parameters["properties"]["w"]
        self.assertEqual((width["exclusiveMinimum"], width["maximum"]), (0, 100000))
        self.assertEqual(
            tools["create_shape"].parameters["properties"]["fillStyle"]["anyOf"][0][
                "enum"
            ],
            ["solid", "hachure", "cross-hatch", "zigzag"],
        )
        self.assertTrue(tools["inspect_scene"].annotations.readOnlyHint)
        self.assertFalse(tools["inspect_scene"].annotations.openWorldHint)
        self.assertTrue(tools["clear"].annotations.destructiveHint)
        self.assertTrue(tools["scene_storage"].annotations.destructiveHint)
        self.assertTrue(tools["export_to_excalidraw_url"].annotations.openWorldHint)
        self.assertTrue(tools["generate_diagram"].annotations.destructiveHint)
        self.assertTrue(all(tool.run_in_thread for tool in tools.values()))

    def test_graph_schema_rejects_unknown_fields_and_has_enums(self):
        schema = self.metadata(create_server(toolset="full"))["generate_diagram"].parameters
        nodes_schema = schema["properties"]["nodes"]
        node_definition = nodes_schema["anyOf"][0]["items"] if "anyOf" in nodes_schema else nodes_schema["items"]
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
            tools["inspect_scene"](mode="element", element_id="missing")
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
                "create_shape",
                {
                    "type": "rectangle",
                    "x": 0,
                    "y": 0,
                    "w": 100,
                    "h": 80,
                    "label": "API",
                },
            )
            inspected = await client.call_tool("inspect_scene", {"mode": "elements"})
            invalid = await client.call_tool(
                "create_shape",
                {
                    "type": "rectangle",
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
                "generate_diagram",
                {
                    "format": "graph",
                    "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
                    "edges": [{"id": "a-to-b", "source": "a", "target": "b"}],
                },
            )
        self.assertFalse(created.is_error)
        self.assertEqual(json.loads(inspected.content[0].text)["total"], 2)
        self.assertTrue(invalid.is_error)
        self.assertTrue(missing.is_error)
        self.assertEqual(json.loads(graph.content[0].text)["node_map"].keys(), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
