"""Comprehensive tests for:
- PNG Export (save to project folder, safe atomic file write, overwrite options)
- Font Support (discovery, category filtering, fallback handling, styling)
- Code Blocks (syntax highlighting, themes, typography, sizing, PNG rendering)
- MCP Protocol End-to-End Tool Invocations
"""

import asyncio
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastmcp import Client
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.fonts import get_font, list_fonts, registry
from excalidraw_mcp.code_blocks import (
    calculate_code_block_dimensions,
    create_code_block,
    get_theme,
    highlight_code,
)
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class PngExportTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.temp_dir = tempfile.mkdtemp()
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

        # Direct default export directory to temp_dir
        self.env_patch = unittest.mock.patch.dict(
            os.environ, {"EXCALIDRAW_EXPORT_DIR": self.temp_dir}
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        # Add some elements to canvas
        self.rect = self.service.add_shape(
            "rectangle",
            100,
            100,
            150,
            80,
            label="Service A",
            roundness="adaptive",
            backgroundColor="#e6f0ff",
            strokeColor="#0066cc",
        )

    def test_export_png_default_directory(self):
        result = self.service.export_png(name="diagram_default")
        self.assertEqual(result["status"], "png exported")
        self.assertEqual(result["name"], "diagram_default.png")
        self.assertTrue(os.path.exists(result["path"]))
        self.assertGreater(result["bytes"], 1000)
        self.assertGreater(result["width"], 100)
        self.assertGreater(result["height"], 100)

        # Verify actual file on disk is valid PNG
        with open(result["path"], "rb") as f:
            header = f.read(8)
            self.assertEqual(header, b"\x89PNG\r\n\x1a\n")

    def test_export_png_custom_directory(self):
        custom_folder = os.path.join(self.temp_dir, "my_project_diagrams")
        result = self.service.export_png(
            name="arch-v1",
            directory=custom_folder,
            scale=1.5,
            padding=30,
        )
        self.assertEqual(result["name"], "arch-v1.png")
        self.assertTrue(os.path.exists(result["path"]))
        self.assertEqual(os.path.dirname(result["path"]), custom_folder)

    def test_export_png_strips_png_extension_cleanly(self):
        result = self.service.export_png(
            name="export_with_ext.png",
            directory=self.temp_dir,
        )
        self.assertEqual(result["name"], "export_with_ext.png")
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "export_with_ext.png")))

    def test_export_png_overwrite_protection(self):
        # First export succeeds
        self.service.export_png(
            name="report",
            directory=self.temp_dir,
            overwrite=False,
        )
        # Second export without overwrite=True must raise SceneError
        with self.assertRaisesRegex(SceneError, "already exists"):
            self.service.export_png(
                name="report",
                directory=self.temp_dir,
                overwrite=False,
            )

        # Second export with overwrite=True succeeds
        res_overwrite = self.service.export_png(
            name="report",
            directory=self.temp_dir,
            overwrite=True,
        )
        self.assertEqual(res_overwrite["status"], "png exported")

    def test_export_png_transparent_background(self):
        res_trans = self.service.export_png(
            name="transparent_view",
            directory=self.temp_dir,
            background=False,
        )
        self.assertTrue(os.path.exists(res_trans["path"]))

    def test_export_png_invalid_parameters(self):
        with self.assertRaisesRegex(SceneError, "cannot be empty"):
            self.service.export_png(name="   ", directory=self.temp_dir)

        with self.assertRaisesRegex(SceneError, "Export name must be"):
            self.service.export_png(name="../../malicious", directory=self.temp_dir)

        with self.assertRaisesRegex(SceneError, "scale"):
            self.service.export_png(name="bad_scale", directory=self.temp_dir, scale=0.1)

        with self.assertRaisesRegex(SceneError, "padding"):
            self.service.export_png(name="bad_pad", directory=self.temp_dir, padding=-10)


class FontSupportTests(unittest.TestCase):
    def test_font_discovery_and_registry(self):
        fonts = list_fonts()
        self.assertIsInstance(fonts, list)
        self.assertGreater(len(fonts), 0)

        # Confirm expected keys in font records
        first = fonts[0]
        self.assertIn("family", first)
        self.assertIn("style", first)
        self.assertIn("category", first)
        self.assertIn("path", first)

    def test_font_category_filtering(self):
        mono_fonts = list_fonts(category="monospace")
        self.assertIsInstance(mono_fonts, list)
        self.assertTrue(all(f["category"] == "monospace" for f in mono_fonts))

        sans_fonts = list_fonts(category="sans-serif")
        self.assertIsInstance(sans_fonts, list)
        self.assertTrue(all(f["category"] == "sans-serif" for f in sans_fonts))

    def test_font_resolution_and_fallback(self):
        # Monospace
        mono_font = get_font("monospace", size=16)
        self.assertIsNotNone(mono_font)

        # Sans-serif
        sans_font = get_font("sans-serif", size=18)
        self.assertIsNotNone(sans_font)

        # Integer fontFamily mapping (Excalidraw 1=handwriting, 2=sans, 3=mono)
        f1 = get_font(1, size=14)
        f2 = get_font(2, size=14)
        f3 = get_font(3, size=14)
        self.assertIsNotNone(f1)
        self.assertIsNotNone(f2)
        self.assertIsNotNone(f3)

        # Non-existent font should gracefully fall back without error
        fallback_font = get_font("CompletelyNonExistentFontFamilyXYZ", size=14)
        self.assertIsNotNone(fallback_font)

    def test_font_dimensions_measurement(self):
        font = get_font("monospace", size=14)
        char_w, line_h = registry.get_char_dimensions(font)
        self.assertGreater(char_w, 0)
        self.assertGreater(line_h, 0)


class CodeBlockTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_create_code_block_element(self):
        code = "def greet(name: str):\n    return f'Hello, {name}!'"
        res = self.service.add_code_block(
            code=code,
            language="python",
            x=50,
            y=50,
            title="greeter.py",
            theme="monokai",
            font_size=14,
            line_numbers=True,
        )

        self.assertEqual(res["status"], "code block created")
        container = self.state.get(res["container_id"])
        self.assertIsNotNone(container)
        self.assertEqual(container["type"], "rectangle")
        self.assertEqual(container["customData"]["language"], "python")
        self.assertEqual(container["customData"]["title"], "greeter.py")
        self.assertEqual(container["customData"]["theme"], "monokai")

        text_el = self.state.get(res["text_id"])
        self.assertIsNotNone(text_el)
        self.assertEqual(text_el["type"], "text")
        self.assertEqual(text_el["fontFamily"], 3)  # Monospace in Excalidraw

    def test_syntax_highlighting_tokens(self):
        code = "const x = 42;\nconsole.log(x);"
        lines = highlight_code(code, language="javascript", theme_name="dark")
        self.assertEqual(len(lines), 2)
        # First line tokens should have colored entries
        self.assertTrue(len(lines[0]) > 0)
        token_texts = [t[0] for t in lines[0]]
        self.assertIn("const", token_texts)

    def test_code_block_dimension_calculation(self):
        short_code = "x = 1"
        long_code = "\n".join([f"line_{i} = 'some long descriptive value for testing'" for i in range(25)])

        w1, h1, g1, _ = calculate_code_block_dimensions(short_code, font_size=14)
        w2, h2, g2, _ = calculate_code_block_dimensions(long_code, font_size=14)

        self.assertGreater(w2, w1)
        self.assertGreater(h2, h1)
        self.assertGreater(g2, 0)

    def test_code_block_inside_frame(self):
        frame_res = self.service.add_frame("Modules", 0, 0, 600, 400)
        cb_res = self.service.add_code_block(
            code="echo 'Deployed'",
            language="bash",
            x=20,
            y=30,
            frame_id=frame_res["frame_id"],
        )
        container = self.state.get(cb_res["container_id"])
        self.assertEqual(container["frameId"], frame_res["frame_id"])

    def test_code_block_in_batch_mutate(self):
        ops = [
            {
                "action": "add_code_block",
                "client_id": "code_snippet",
                "code": "SELECT * FROM users WHERE active = 1;",
                "language": "sql",
                "x": 100,
                "y": 100,
                "theme": "light",
            }
        ]
        res = self.service.batch_mutate(ops)
        self.assertEqual(res["status"], "batch executed")
        self.assertIn("code_snippet", res["ref_map"])
        snippet_id = res["ref_map"]["code_snippet"]
        container = self.state.get(snippet_id)
        self.assertEqual(container["customData"]["language"], "sql")

    def test_add_code_block_validation(self):
        with self.assertRaisesRegex(SceneError, "cannot be empty"):
            self.service.add_code_block(code="   ")

        with self.assertRaisesRegex(SceneError, "finite"):
            self.service.add_code_block(code="pass", x=float("nan"), y=0)

        with self.assertRaisesRegex(SceneError, "font_size"):
            self.service.add_code_block(code="pass", font_size=4)

        with self.assertRaisesRegex(SceneError, "w must be a positive"):
            self.service.add_code_block(code="pass", w=-50)


class MCPProtocolEndToEndTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_export_png_and_code_blocks(self):
        server = create_server(toolset="full")
        async with Client(server, timeout=5) as client:
            # 1. Test list_fonts
            fonts_res = await client.call_tool("list_fonts", {"category": "monospace"})
            self.assertFalse(fonts_res.is_error)
            self.assertIn("total", fonts_res.structured_content)
            self.assertIn("fonts", fonts_res.structured_content)

            # 2. Test add_code_block
            cb_res = await client.call_tool(
                "add_code_block",
                {
                    "code": "def solve():\n    return 42",
                    "language": "python",
                    "title": "solution.py",
                    "x": 50,
                    "y": 50,
                    "theme": "dark",
                },
            )
            self.assertFalse(cb_res.is_error)
            container_id = cb_res.structured_content["container_id"]
            self.assertIsNotNone(container_id)

            # 3. Test export_png
            with tempfile.TemporaryDirectory() as tmp_dir:
                export_res = await client.call_tool(
                    "export_png",
                    {
                        "name": "protocol_export_test",
                        "directory": tmp_dir,
                        "scale": 1.0,
                        "padding": 20,
                    },
                )
                self.assertFalse(export_res.is_error)
                content = export_res.structured_content
                self.assertEqual(content["status"], "png exported")
                self.assertTrue(os.path.exists(content["path"]))


if __name__ == "__main__":
    unittest.main()
