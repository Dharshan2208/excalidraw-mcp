"""Tests for Excalifont integration, discovery, rendering, persistence, and MCP tools."""

import asyncio
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

from fastmcp import Client

from excalidraw_mcp.elements import normalize_font_family, text, rect
from excalidraw_mcp.fonts import FontRegistry, get_font, list_fonts, registry
from excalidraw_mcp.renderer import render_scene_image, render_scene_to_png
from excalidraw_mcp.service import SceneService, _label_for
from excalidraw_mcp.server import create_server


class TestFontRegistryAndExcalifontDiscovery(unittest.TestCase):
    def test_bundled_excalifont_exists(self):
        assets_dir = Path(__file__).resolve().parent.parent / "excalidraw_mcp" / "assets" / "fonts"
        font_file = assets_dir / "Excalifont-Regular.ttf"
        license_file = assets_dir / "OFL.txt"
        self.assertTrue(font_file.is_file(), f"Font file missing at {font_file}")
        self.assertTrue(license_file.is_file(), f"License file missing at {license_file}")
        self.assertGreater(font_file.stat().st_size, 50_000)

    def test_registry_discovers_excalifont(self):
        reg = FontRegistry()
        reg.discover(force=True)
        self.assertIn("excalifont", reg._by_family)
        records = reg._by_family["excalifont"]
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["family"], "Excalifont")
        self.assertEqual(records[0]["category"], "handwriting")
        self.assertEqual(records[0]["style"], "Regular")

    def test_get_font_by_int_and_family_name(self):
        # By integer 1 (Excalidraw schema code for Excalifont/Virgil)
        font_by_int = get_font(1, 24)
        self.assertEqual(font_by_int.getname(), ("Excalifont", "Regular"))

        # By family name (case-insensitive)
        font_by_name = get_font("excalifont", 24)
        self.assertEqual(font_by_name.getname(), ("Excalifont", "Regular"))

        font_by_upper = get_font("Excalifont", 24)
        self.assertEqual(font_by_upper.getname(), ("Excalifont", "Regular"))

        # By alias 'virgil'
        font_by_alias = get_font("virgil", 24)
        self.assertEqual(font_by_alias.getname(), ("Excalifont", "Regular"))

        # By category 'handwriting'
        font_by_cat = get_font("handwriting", 24)
        self.assertEqual(font_by_cat.getname(), ("Excalifont", "Regular"))

    def test_fallback_when_invalid_font_requested(self):
        # Non-existent font should gracefully fall back to a valid ImageFont without crashing
        font = get_font("completely_nonexistent_font_12345", 18)
        self.assertIsNotNone(font)
        bbox = font.getbbox("Hello")
        self.assertGreater(bbox[2], bbox[0])

    def test_latin_glyph_support_filter(self):
        # sans-serif should select a font with valid Latin glyphs (not Droid Sans Ethiopic or other non-Latin fonts)
        font = get_font("sans-serif", 20)
        self.assertIsNotNone(font)
        # Verify masks for 'A' and '?' are distinct (not falling back to ? for English letters)
        mask_a = list(font.getmask("A"))
        mask_q = list(font.getmask("?"))
        self.assertNotEqual(mask_a, mask_q)

    def test_fallback_when_bundled_font_missing(self):
        # Empty registry with no fonts found should fall back to Pillow default
        empty_reg = FontRegistry()
        with patch.object(empty_reg, "_scan_directory"):
            with patch("shutil.which", return_value=None):
                with patch("excalidraw_mcp.fonts._get_font_directories", return_value=[]):
                    empty_reg.discover(force=True)
                    font = empty_reg.load_font(family="excalifont", size=20)
                    self.assertIsNotNone(font)
                    bbox = font.getbbox("Fallback Test")
                    self.assertIsNotNone(bbox)


class TestFontNormalizationAndElements(unittest.TestCase):
    def test_normalize_font_family_mappings(self):
        self.assertEqual(normalize_font_family(None), 2)
        self.assertEqual(normalize_font_family(1), 1)
        self.assertEqual(normalize_font_family(2), 2)
        self.assertEqual(normalize_font_family(3), 3)
        self.assertEqual(normalize_font_family(4), 4)
        self.assertEqual(normalize_font_family("1"), 1)
        self.assertEqual(normalize_font_family("excalifont"), 1)
        self.assertEqual(normalize_font_family("Excalifont"), 1)
        self.assertEqual(normalize_font_family("virgil"), 1)
        self.assertEqual(normalize_font_family("handwriting"), 1)
        self.assertEqual(normalize_font_family("hand"), 1)
        self.assertEqual(normalize_font_family("sans-serif"), 2)
        self.assertEqual(normalize_font_family("helvetica"), 2)
        self.assertEqual(normalize_font_family("monospace"), 3)
        self.assertEqual(normalize_font_family("code"), 3)
        self.assertEqual(normalize_font_family("cascadia"), 3)
        self.assertEqual(normalize_font_family("comic-shanns"), 4)
        self.assertEqual(normalize_font_family("unknown-random-font"), 2)

    def test_text_element_creation_with_font_family(self):
        el_default = text(0, 0, "Default text")
        self.assertEqual(el_default["fontFamily"], 2)

        el_excalifont = text(0, 0, "Handwritten note", fontFamily="excalifont")
        self.assertEqual(el_excalifont["fontFamily"], 1)

        el_int = text(0, 0, "Integer font", fontFamily=1)
        self.assertEqual(el_int["fontFamily"], 1)

        el_kwarg = text(0, 0, "Kwarg font", font_family="excalifont")
        self.assertEqual(el_kwarg["fontFamily"], 1)


class TestSceneServiceExcalifontOperations(unittest.TestCase):
    def test_add_text_with_excalifont(self):
        service = SceneService()
        res = service.add_text(100, 200, "Architectural Draft", font_size=24, font_family="excalifont")
        txt_id = res["text_id"]
        el_info = service.get_element(txt_id)
        el = el_info["element"]
        self.assertEqual(el["fontFamily"], 1)
        self.assertEqual(el["fontSize"], 24)
        self.assertEqual(el["text"], "Architectural Draft")

    def test_update_element_font_family(self):
        service = SceneService()
        res = service.add_text(50, 50, "Update me", font_size=16)
        txt_id = res["text_id"]
        self.assertEqual(service.get_element(txt_id)["element"]["fontFamily"], 2)

        service.update_element(txt_id, font_family="excalifont", font_size=28)
        updated = service.get_element(txt_id)["element"]
        self.assertEqual(updated["fontFamily"], 1)
        self.assertEqual(updated["fontSize"], 28)

    def test_shape_label_with_excalifont(self):
        service = SceneService()
        res = service.add_shape("rectangle", 10, 10, 120, 80, label="Box Title", font_family="excalifont")
        rect_id = res["rectangle_id"]
        lbl_id = res["label_id"]
        self.assertIsNotNone(lbl_id)
        lbl = service.get_element(lbl_id)["element"]
        self.assertEqual(lbl["fontFamily"], 1)

    def test_update_shape_label_font(self):
        service = SceneService()
        res = service.add_shape("rectangle", 0, 0, 100, 50, label="Initial")
        rect_id = res["rectangle_id"]
        lbl_id = res["label_id"]
        self.assertEqual(service.get_element(lbl_id)["element"]["fontFamily"], 2)

        service.update_element(rect_id, font_family="excalifont")
        lbl = service.get_element(lbl_id)["element"]
        self.assertEqual(lbl["fontFamily"], 1)

    def test_batch_mutate_with_excalifont(self):
        service = SceneService()
        ops = [
            {
                "action": "add_text",
                "client_id": "txt1",
                "x": 100,
                "y": 100,
                "content": "Batch Note",
                "font_family": "excalifont",
                "font_size": 22,
            },
            {
                "action": "add_rectangle",
                "client_id": "box1",
                "x": 200,
                "y": 200,
                "w": 150,
                "h": 100,
                "label": "Box",
            },
            {
                "action": "update_element",
                "element_id": "box1",
                "font_family": "excalifont",
            },
        ]
        res = service.batch_mutate(ops)
        self.assertEqual(res["operations_executed"], 3)
        txt_id = res["ref_map"]["txt1"]
        box_id = res["ref_map"]["box1"]
        self.assertEqual(service.get_element(txt_id)["element"]["fontFamily"], 1)
        lbl = _label_for(_active_dict(service), box_id)
        self.assertEqual(lbl["fontFamily"], 1)

    def test_list_fonts_includes_excalifont(self):
        service = SceneService()
        fonts_res = service.list_fonts()
        self.assertEqual(fonts_res["defaults"].get("handwriting"), "Excalifont")
        names = [f["family"] for f in fonts_res["fonts"]]
        self.assertIn("Excalifont", names)

    def test_draw_graph_with_excalifont(self):
        service = SceneService()
        nodes = [
            {"id": "n1", "label": "Node 1", "font_family": "excalifont", "font_size": 22},
            {"id": "n2", "label": "Node 2"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2", "label": "Flows", "font_family": "excalifont"},
        ]
        res = service.draw_graph(nodes, edges, font_family="excalifont")
        self.assertEqual(res["status"], "graph drawn")
        doc = service.state.document()
        texts = [el for el in doc["elements"] if el["type"] == "text"]
        self.assertEqual(len(texts), 3)  # 2 node labels + 1 edge label
        for t in texts:
            self.assertEqual(t["fontFamily"], 1)  # All configured with Excalifont

    def test_draw_architecture_with_excalifont(self):
        service = SceneService()
        res = service.draw_architecture("box: Client, box: Server", font_family="excalifont")
        self.assertEqual(res["status"], "graph drawn")
        doc = service.state.document()
        node_texts = [el for el in doc["elements"] if el["type"] == "text"]
        self.assertGreaterEqual(len(node_texts), 2)
        for t in node_texts:
            self.assertEqual(t["fontFamily"], 1)

    def test_add_shapes_and_connect_with_font_properties(self):
        service = SceneService()
        r = service.add_shape("rectangle", 0, 0, 100, 50, label="Box", font_family="excalifont", font_size=18)
        c = service.add_shape("ellipse", 200, 0, 50, 50, label="Circle", font_family="excalifont", font_size=16)
        conn = service.connect(r["rectangle_id"], c["circle_id"], label="Links", font_family="excalifont", font_size=14)

        lbl_r = service.get_element(r["label_id"])["element"]
        self.assertEqual(lbl_r["fontFamily"], 1)
        self.assertEqual(lbl_r["fontSize"], 18)

        lbl_c = service.get_element(c["label_id"])["element"]
        self.assertEqual(lbl_c["fontFamily"], 1)
        self.assertEqual(lbl_c["fontSize"], 16)

        lbl_conn = service.get_element(conn["label_id"])["element"]
        self.assertEqual(lbl_conn["fontFamily"], 1)
        self.assertEqual(lbl_conn["fontSize"], 14)


class TestRenderingAndExportCompatibility(unittest.TestCase):
    def test_render_png_with_excalifont(self):
        service = SceneService()
        service.add_text(50, 50, "Excalifont Heading", font_size=32, font_family="excalifont")
        service.add_shape("rectangle", 50, 120, 200, 100, label="Annotated Node", font_family="excalifont")
        service.add_text(50, 250, "Standard Sans-serif Text", font_size=20, font_family="sans-serif")
        service.add_text(50, 300, "def foo(): pass", font_size=18, font_family="monospace")

        doc, _ = service.state.snapshot()
        png_bytes, width, height = render_scene_image(doc, scale=1.0)
        self.assertGreater(len(png_bytes), 0)
        self.assertTrue(width > 0 and height > 0)

        # Verify PIL can open the generated PNG image
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.format, "PNG")
        self.assertEqual(img.size, (width, height))

    def test_export_scene_and_url_preserves_font_family(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": tmp_dir}):
                service = SceneService()
                service.add_text(100, 100, "Web URL Note", font_size=20, font_family="excalifont")

                # Test export_to_excalidraw_url
                url_res = service.export_to_excalidraw_url()
                self.assertIn("url", url_res)
                self.assertTrue(url_res["url"].startswith("https://excalidraw.com/#json="))

                # Test save and load
                service.save("excalifont_scene")

                # Load into fresh service
                new_service = SceneService()
                new_service.load("excalifont_scene")
                doc, _ = new_service.state.snapshot()
                text_elements = [el for el in doc["elements"] if el["type"] == "text"]
                self.assertEqual(len(text_elements), 1)
                self.assertEqual(text_elements[0]["fontFamily"], 1)
                self.assertEqual(text_elements[0]["text"], "Web URL Note")


class TestMcpServerExcalifontToolCalls(unittest.IsolatedAsyncioTestCase):
    def test_mcp_server_add_text_tool_excalifont(self):
        server = create_server()
        tools = {t.name: t for t in asyncio.run(server.list_tools())}
        self.assertIn("add_text", tools)
        schema = tools["add_text"].parameters
        self.assertIn("font_family", schema.get("properties", {}))

    def test_mcp_server_update_element_tool_font_properties(self):
        server = create_server()
        tools = {t.name: t for t in asyncio.run(server.list_tools())}
        self.assertIn("update_element", tools)
        schema = tools["update_element"].parameters
        self.assertIn("font_family", schema.get("properties", {}))
        self.assertIn("font_size", schema.get("properties", {}))

    def test_mcp_server_draw_graph_tool_font_properties(self):
        server = create_server(toolset="full")
        tools = {t.name: t for t in asyncio.run(server.list_tools())}
        self.assertIn("draw_graph", tools)
        schema = tools["draw_graph"].parameters
        self.assertIn("font_family", schema.get("properties", {}))
        self.assertIn("font_size", schema.get("properties", {}))
        # Node properties also accept font_family
        node_props = schema["properties"]["nodes"]["items"]["properties"]
        self.assertIn("font_family", node_props)
        self.assertIn("font_size", node_props)

    async def test_mcp_client_tool_call_creates_excalifont_text(self):
        server = create_server()
        async with Client(server, timeout=5) as client:
            res = await client.call_tool(
                "add_text",
                {
                    "x": 100,
                    "y": 150,
                    "content": "MCP Agent handwritten text",
                    "font_size": 24,
                    "font_family": "excalifont",
                },
            )
            self.assertFalse(res.is_error)
            txt_id = res.structured_content["text_id"]

            elem_res = await client.call_tool("get_element", {"element_id": txt_id})
            self.assertFalse(elem_res.is_error)
            element = elem_res.structured_content["element"]
            self.assertEqual(element["fontFamily"], 1)
            self.assertEqual(element["fontSize"], 24)
            self.assertEqual(element["text"], "MCP Agent handwritten text")


def _active_dict(service):
    doc, _ = service.state.snapshot()
    return {el["id"]: el for el in doc["elements"] if not el.get("isDeleted")}


if __name__ == "__main__":
    unittest.main()
