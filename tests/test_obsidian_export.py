"""Unit and integration tests for Obsidian Excalidraw plugin (.excalidraw.md) export."""

import json
import os
import tempfile
from pathlib import Path
import unittest

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.obsidian import (
    OBSIDIAN_EXCALIDRAW_HEADER,
    parse_obsidian_markdown,
    serialize_obsidian_markdown,
)
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService
from fastmcp import Client


class TestObsidianSerialization(unittest.TestCase):
    def test_serialize_empty_document(self):
        doc = {"type": "excalidraw", "version": 2, "elements": [], "appState": {}}
        md = serialize_obsidian_markdown(doc)
        self.assertIn("excalidraw-plugin: parsed", md)
        self.assertIn("tags: [excalidraw]", md)
        self.assertIn("# Drawing", md)
        parsed = parse_obsidian_markdown(md)
        self.assertEqual(parsed["type"], "excalidraw")
        self.assertEqual(parsed["elements"], [])

    def test_serialize_escapes_percent_percent(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {
                    "id": "t1",
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "text": "Discount %% Special",
                }
            ],
            "appState": {},
        }
        md = serialize_obsidian_markdown(doc)
        # Verify that %% was sanitized in the # Text Elements comment block
        text_section = md.split("# Drawing")[0]
        self.assertNotIn("Discount %% Special", text_section)
        self.assertIn("Discount % % Special", text_section)

    def test_export_obsidian_rejects_dir_destination(self):
        service = SceneService()
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_target = Path(tmp_dir) / "dir_conflict.excalidraw.md"
            dir_target.mkdir()
            with self.assertRaisesRegex(SceneError, "not a regular file"):
                service.export_obsidian("dir_conflict", directory=tmp_dir, overwrite=True)

    def test_serialize_text_elements_and_block_references(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {
                    "id": "rect1",
                    "type": "rectangle",
                    "x": 0,
                    "y": 0,
                    "width": 100,
                    "height": 50,
                    "isDeleted": False,
                },
                {
                    "id": "text1",
                    "type": "text",
                    "text": "Hello World\nLine 2",
                    "x": 10,
                    "y": 10,
                    "width": 80,
                    "height": 30,
                    "isDeleted": False,
                },
                {
                    "id": "text_deleted",
                    "type": "text",
                    "text": "Should not appear in text elements",
                    "isDeleted": True,
                },
            ],
            "appState": {"viewBackgroundColor": "#ffffff"},
        }
        md = serialize_obsidian_markdown(doc)
        text_elements_section = md.split("%%\n# Drawing")[0]
        self.assertIn("Hello World Line 2 ^text1", text_elements_section)
        self.assertNotIn("Should not appear in text elements", text_elements_section)
        self.assertIn("```json\n", md)

        parsed = parse_obsidian_markdown(md)
        self.assertEqual(len(parsed["elements"]), 3)
        self.assertEqual(parsed["elements"][1]["id"], "text1")
        self.assertEqual(parsed["elements"][1]["text"], "Hello World\nLine 2")

    def test_roundtrip_complex_scene(self):
        doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": [
                {
                    "id": "elem-1",
                    "type": "diamond",
                    "x": 120,
                    "y": 80,
                    "width": 160,
                    "height": 80,
                    "backgroundColor": "#ffd8a8",
                    "strokeColor": "#d9480f",
                    "strokeWidth": 2,
                    "label": {"text": "Decision ☕", "fontSize": 16},
                },
                {
                    "id": "txt-utf8",
                    "type": "text",
                    "text": "Unicode: 日本語 & Café 🌟",
                    "x": 120,
                    "y": 200,
                },
            ],
            "appState": {"gridSize": 20},
        }
        md = serialize_obsidian_markdown(doc)
        parsed = parse_obsidian_markdown(md)
        self.assertEqual(parsed["elements"][0]["type"], "diamond")
        self.assertEqual(parsed["elements"][1]["text"], "Unicode: 日本語 & Café 🌟")
        self.assertEqual(parsed["appState"]["gridSize"], 20)

    def test_parse_invalid_content(self):
        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            parse_obsidian_markdown("")

        with self.assertRaisesRegex(ValueError, "cannot be empty"):
            parse_obsidian_markdown("   \n\t  ")

        with self.assertRaisesRegex(ValueError, "could not find embedded JSON code block"):
            parse_obsidian_markdown("# Just some markdown\nNo code block here.")

        with self.assertRaisesRegex(ValueError, "Failed to decode Excalidraw JSON"):
            parse_obsidian_markdown("# Drawing\n```json\n{ invalid json here\n```\n")

        with self.assertRaisesRegex(ValueError, "Expected JSON object"):
            parse_obsidian_markdown("# Drawing\n```json\n[1, 2, 3]\n```\n")


class TestObsidianServiceExport(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.service.add_shape("rectangle", 50, 50, 120, 80)
        self.service.add_shape("ellipse", 250, 50, 100, 80)
        self.service.add_arrow(170, 90, 250, 90)

    def test_export_obsidian_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = self.service.export_obsidian(name="my_diagram", directory=tmp_dir)
            self.assertEqual(res["status"], "obsidian exported")
            self.assertEqual(res["name"], "my_diagram.excalidraw.md")
            self.assertEqual(res["format"], "obsidian")
            self.assertEqual(res["elements"], 3)
            self.assertTrue(os.path.exists(res["path"]))

            content = Path(res["path"]).read_text(encoding="utf-8")
            self.assertIn("excalidraw-plugin: parsed", content)
            self.assertIn("# Drawing", content)

            # Verify round-trip parsing
            doc = parse_obsidian_markdown(content)
            self.assertEqual(len(doc["elements"]), 3)

    def test_export_obsidian_name_cleaning(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = self.service.export_obsidian(name="architecture.excalidraw.md", directory=tmp_dir)
            self.assertEqual(res["name"], "architecture.excalidraw.md")
            self.assertTrue(Path(res["path"]).exists())

    def test_export_obsidian_collision_guard(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            self.service.export_obsidian(name="collision_test", directory=tmp_dir)
            with self.assertRaisesRegex(SceneError, "already exists"):
                self.service.export_obsidian(name="collision_test", directory=tmp_dir, overwrite=False)

            # With overwrite=True, it should succeed
            res2 = self.service.export_obsidian(name="collision_test", directory=tmp_dir, overwrite=True)
            self.assertEqual(res2["status"], "obsidian exported")

    def test_export_obsidian_path_traversal_guard(self):
        with self.assertRaisesRegex(SceneError, "outside permitted"):
            self.service.export_obsidian(name="traversal", directory="/etc")

    def test_export_obsidian_invalid_names(self):
        with self.assertRaisesRegex(SceneError, "cannot be empty"):
            self.service.export_obsidian(name="")

        with self.assertRaisesRegex(SceneError, "Export name must be"):
            self.service.export_obsidian(name="../invalid_name")

    def test_save_service_delegates_to_obsidian(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = self.service.save(name="delegated_test", format="obsidian", directory=tmp_dir)
            self.assertEqual(res["status"], "obsidian exported")
            self.assertEqual(res["format"], "obsidian")
            self.assertTrue(Path(res["path"]).exists())

    def test_export_scene_obsidian_detached_snapshot(self):
        md_text = self.service.export_scene(format="obsidian")
        self.assertIn("excalidraw-plugin: parsed", md_text)
        self.assertIn("```json\n", md_text)
        doc = parse_obsidian_markdown(md_text)
        self.assertEqual(len(doc["elements"]), 3)

    def test_import_exported_obsidian_scene(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = self.service.export_obsidian(name="roundtrip", directory=tmp_dir)
            file_path = res["path"]

            new_service = SceneService()
            import_res = new_service.import_scene(data=file_path, mode="replace")
            self.assertEqual(import_res["elements_imported"], 3)
            self.assertEqual(len(new_service.state.all()), 3)


class TestObsidianMcpIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SceneService()
        self.service.add_shape("rectangle", 0, 0, 100, 60)
        self.server = create_server(self.service, toolset="full")

    async def test_scene_storage_save_obsidian(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            async with Client(self.server, timeout=5) as client:
                res = await client.call_tool(
                    "scene_storage",
                    {
                        "action": "save",
                        "name": "mcp_exported_scene",
                        "format": "obsidian",
                        "directory": tmp_dir,
                    },
                )
                self.assertFalse(res.is_error)
                data = json.loads(res.content[0].text)
                self.assertEqual(data["status"], "obsidian exported")
                self.assertEqual(data["format"], "obsidian")
                self.assertTrue(Path(data["path"]).exists())

    async def test_scene_storage_export_obsidian(self):
        async with Client(self.server, timeout=5) as client:
            res = await client.call_tool(
                "scene_storage",
                {
                    "action": "export",
                    "format": "obsidian",
                },
            )
            self.assertFalse(res.is_error)
            content_block = res.content[0]
            self.assertEqual(content_block.type, "resource")
            self.assertEqual(content_block.resource.mimeType, "text/markdown")
            self.assertTrue(str(content_block.resource.uri).endswith(".excalidraw.md"))
            self.assertIn("excalidraw-plugin: parsed", content_block.resource.text)
