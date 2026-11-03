import asyncio
import unittest

from fastmcp import Client

from excalidraw_mcp.elements import bind_text, rect, text
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.layout import boundary_point, layered_layout
from excalidraw_mcp.models import new_document
from excalidraw_mcp.parser import parse_architecture
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class AuditFixesServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_update_element_preserves_style_when_label_empty(self):
        shape = self.service.add_shape("rectangle", 0, 0, 100, 100)
        rect_id = shape["rectangle_id"]
        result = self.service.update_element(
            rect_id, label="", stroke_color="#ff0000", opacity=80
        )
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["element_id"], rect_id)
        self.assertIsNone(result["label_id"])
        updated = self.state.get(rect_id)
        self.assertEqual(updated["strokeColor"], "#ff0000")
        self.assertEqual(updated["opacity"], 80)

    def test_update_element_on_bound_label_directly_recenters_on_container(self):
        shape = self.service.add_shape(
            "rectangle", 200, 100, 100, 100, label="Init"
        )
        label_id = shape["label_id"]
        result = self.service.update_element(
            label_id, label="A much longer label that wraps onto multiple lines\nof text"
        )
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["label_id"], label_id)
        label = self.state.get(label_id)
        container = self.state.get(shape["rectangle_id"])
        cx = container["x"] + container["width"] / 2
        cy = container["y"] + container["height"] / 2
        self.assertAlmostEqual(label["x"] + label["width"] / 2, cx)
        self.assertAlmostEqual(label["y"] + label["height"] / 2, cy)

    def test_clear_bound_label_via_label_id(self):
        shape = self.service.add_shape("rectangle", 0, 0, 100, 100, label="To Delete")
        label_id = shape["label_id"]
        rect_id = shape["rectangle_id"]
        result = self.service.update_element(label_id, label="")
        self.assertEqual(result["status"], "updated")
        self.assertIsNone(result["label_id"])
        self.assertIsNone(self.state.get(label_id))
        self.assertEqual(self.state.get(rect_id)["boundElements"], [])

    def test_update_style_on_bound_label_directly(self):
        shape = self.service.add_shape("rectangle", 0, 0, 100, 100, label="Text")
        label_id = shape["label_id"]
        result = self.service.update_element(label_id, stroke_color="#0000ff", opacity=70)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["label_id"], label_id)
        label = self.state.get(label_id)
        self.assertEqual(label["strokeColor"], "#0000ff")
        self.assertEqual(label["opacity"], 70)

    def test_arrow_late_label_font_size(self):
        arr = self.service.add_arrow(0, 0, 100, 100)
        result = self.service.update_element(arr["arrow_id"], label="Midpoint")
        self.assertIsNotNone(result["label_id"])
        label = self.state.get(result["label_id"])
        self.assertEqual(label["fontSize"], 14)

    def test_resize_rejects_elbowed_or_rotated_arrow(self):
        shape_a = rect(0, 0, 100, 100)
        shape_b = rect(300, 0, 100, 100)
        arr = {
            "id": "arrow-1",
            "type": "arrow",
            "x": 100,
            "y": 50,
            "points": [[0, 0], [200, 0]],
            "startBinding": {"elementId": shape_a["id"]},
            "endBinding": {"elementId": shape_b["id"]},
            "elbowed": True,
        }
        self.state.replace(new_document([shape_a, shape_b, arr]))
        with self.assertRaisesRegex(SceneError, "not supported yet"):
            self.service.resize(shape_a["id"], 150, 150)

    def test_boundary_point_zero_dimension_safe(self):
        node = {"shape": "rectangle", "x": 10, "y": 20, "w": 0, "h": 0}
        target = {"shape": "rectangle", "x": 100, "y": 20, "w": 50, "h": 50}
        pt = boundary_point(node, target)
        self.assertEqual(len(pt), 2)
        self.assertTrue(all(isinstance(v, (int, float)) for v in pt))

    def test_parser_markdown_numbered_and_bullet_lists(self):
        prompt = "1. box: API Gateway\n2. circle: Main DB\n* diamond: Auth Router"
        nodes = parse_architecture(prompt)
        self.assertEqual(len(nodes), 3)
        self.assertEqual(nodes[0]["shape"], "rectangle")
        self.assertEqual(nodes[0]["label"], "API Gateway")
        self.assertEqual(nodes[1]["shape"], "ellipse")
        self.assertEqual(nodes[1]["label"], "Main DB")
        self.assertEqual(nodes[2]["shape"], "diamond")
        self.assertEqual(nodes[2]["label"], "Auth Router")

    def test_text_crlf_normalization(self):
        el = text(0, 0, "Line 1\r\nLine 2\rLine 3")
        self.assertEqual(el["text"], "Line 1\nLine 2\nLine 3")
        self.assertNotIn("\r", el["text"])
        self.assertNotIn("\r", el["originalText"])

    def test_bind_text_inherits_container_angle(self):
        container = rect(0, 0, 100, 100)
        container["angle"] = 0.785
        label = text(0, 0, "Rotated")
        bind_text(label, container)
        self.assertEqual(label["angle"], 0.785)

    def test_layered_layout_error_message_is_actionable(self):
        nodes = [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
        edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}]
        with self.assertRaisesRegex(
            SceneError, "Use layout='horizontal' or 'vertical'"
        ):
            layered_layout(nodes, edges)


class AuditFixesMCPContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_output_schemas_are_concrete_typed_dicts(self):
        server = create_server(toolset="full")
        tools = {tool.name: tool for tool in await server.list_tools()}

        self.assertIn("deleted_ids", tools["delete"].output_schema["properties"])
        self.assertIn("x", tools["move"].output_schema["properties"])
        self.assertIn("y", tools["move"].output_schema["properties"])
        self.assertIn("path", tools["save"].output_schema["properties"])
        self.assertIn("scenes", tools["list_saved_scenes"].output_schema["properties"])
        self.assertIn("label_id", tools["update_element"].output_schema["properties"])
        self.assertIn("width", tools["resize"].output_schema["properties"])
        self.assertIn("arrow_id", tools["connect"].output_schema["properties"])
        self.assertIn("history_depth", tools["undo"].output_schema["properties"])
        self.assertIn("loaded", tools["load"].output_schema["properties"])
        self.assertIn("next_step", tools["draw_architecture"].output_schema["properties"])

    async def test_protocol_rejects_coerced_booleans_in_pagination(self):
        async with Client(create_server(), timeout=5) as client:
            res1 = await client.call_tool(
                "get_scene", {"offset": True}, raise_on_error=False
            )
            self.assertTrue(res1.is_error)
            res2 = await client.call_tool(
                "get_scene", {"limit": True}, raise_on_error=False
            )
            self.assertTrue(res2.is_error)

    async def test_protocol_rejects_empty_content_in_add_text_and_draw_architecture(
        self,
    ):
        async with Client(create_server(), timeout=5) as client:
            res1 = await client.call_tool(
                "add_text",
                {"x": 0, "y": 0, "content": "   "},
                raise_on_error=False,
            )
            self.assertTrue(res1.is_error)
            res2 = await client.call_tool(
                "draw_architecture",
                {"prompt": "   "},
                raise_on_error=False,
            )
            self.assertTrue(res2.is_error)

    async def test_arrow_and_connect_accept_roughness(self):
        service = SceneService()
        server = create_server(service)
        async with Client(server, timeout=5) as client:
            arrow_res = await client.call_tool(
                "add_arrow",
                {"x": 0, "y": 0, "x2": 100, "y2": 100, "roughness": 2},
            )
            arrow_id = arrow_res.structured_content["arrow_id"]
            self.assertEqual(service.state.get(arrow_id)["roughness"], 2)

            rect_a = await client.call_tool(
                "add_rectangle", {"x": 0, "y": 0, "w": 50, "h": 50}
            )
            rect_b = await client.call_tool(
                "add_rectangle", {"x": 200, "y": 0, "w": 50, "h": 50}
            )
            connect_res = await client.call_tool(
                "connect",
                {
                    "source_id": rect_a.structured_content["rectangle_id"],
                    "target_id": rect_b.structured_content["rectangle_id"],
                    "roughness": 3,
                },
            )
            conn_id = connect_res.structured_content["arrow_id"]
            self.assertEqual(service.state.get(conn_id)["roughness"], 3)


if __name__ == "__main__":
    unittest.main()
