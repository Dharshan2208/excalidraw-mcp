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
                ["excalidraw://scenes/{name}.excalidraw", "excalidraw://guide/{topic}"],
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


    async def test_active_scene_resource(self):
        """Active scene can be read directly via excalidraw://active/scene.json and excalidraw://active."""
        service = SceneService()
        service.add_shape("rectangle", 10, 20, 100, 50, label="Resource Box")
        server = create_server(service)

        # 1. Read excalidraw://active/scene.json
        res_json = await server.read_resource("excalidraw://active/scene.json")
        self.assertTrue(len(res_json.contents) > 0)
        data_json = json.loads(res_json.contents[0].content)
        self.assertEqual(data_json["type"], "excalidraw")
        self.assertEqual(data_json["version"], 2)
        texts = [el for el in data_json["elements"] if el["type"] == "text"]
        self.assertEqual(texts[0]["text"], "Resource Box")

        # 2. Read excalidraw://active alias
        res_alias = await server.read_resource("excalidraw://active")
        self.assertTrue(len(res_alias.contents) > 0)
        data_alias = json.loads(res_alias.contents[0].content)
        self.assertEqual(data_alias["type"], "excalidraw")

    async def test_auto_fix_layout_progress_reporting(self):
        """auto_fix_layout executes cleanly with FastMCP Context progress reporting."""
        service = SceneService()
        service.add_shape("rectangle", 0, 0, 100, 100, label="Box 1")
        service.add_shape("rectangle", 20, 20, 100, 100, label="Box 2")  # Overlapping
        server = create_server(service)

        progress_calls = []

        class MockContext:
            async def report_progress(self, progress: float, total: float | None = None, message: str | None = None):
                progress_calls.append((progress, total, message))

        # Test tool handler with MockContext directly inside AnyIO worker thread
        import anyio
        tool = await server.get_tool("auto_fix_layout")
        tool_fn = tool.fn
        await anyio.to_thread.run_sync(lambda: tool_fn(dry_run=False, repair_scope="all", ctx=MockContext()))
        self.assertGreaterEqual(len(progress_calls), 5)
        self.assertEqual(progress_calls[0][0], 1)
        self.assertEqual(progress_calls[-1][0], 5)

        async with Client(server) as client:
            res = await client.call_tool("auto_fix_layout", {"dry_run": False, "repair_scope": "all"})
            self.assertFalse(res.is_error)
            data = json.loads(res.content[0].text)
            self.assertIn("status", data)
            self.assertIn("applied_change_count", data)


if __name__ == "__main__":
    unittest.main()
