"""Tests for headless vector SVG rendering and export_svg tool."""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

from fastmcp import Client

from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService, SceneError
from excalidraw_mcp.svg_renderer import render_scene_svg


class SvgRendererTests(unittest.TestCase):
    def test_render_empty_scene_svg(self):
        """Rendering an empty scene produces well-formed SVG XML."""
        doc = {"type": "excalidraw", "version": 2, "elements": []}
        svg_str, w, h = render_scene_svg(doc, padding=20)
        self.assertTrue(svg_str.startswith("<?xml"))
        self.assertIn("<svg", svg_str)
        self.assertIn("</svg>", svg_str)
        # Verify valid XML
        root = ET.fromstring(svg_str)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")

    def test_render_shapes_and_connectors_svg(self):
        """Rendering rectangles, ellipses, diamonds, arrows, and labels generates valid SVG elements."""
        service = SceneService()
        r = service.add_shape("rectangle", 50, 50, 120, 60, label="Start Box", font_family="excalifont")
        c = service.add_shape("ellipse", 250, 50, 80, 80, label="Decision", font_family="sans-serif")
        d = service.add_shape("diamond", 400, 40, 100, 100, label="Outcome", font_family="monospace")
        service.connect(r["rectangle_id"], c["circle_id"], label="Process", start_arrowhead="bar", end_arrowhead="triangle")
        service.connect(c["circle_id"], d["diamond_id"], label="Evaluate", start_arrowhead="dot", end_arrowhead="diamond")

        doc, _ = service.state.snapshot()
        svg_str, w, h = render_scene_svg(doc, padding=40, background=True)

        root = ET.fromstring(svg_str)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        self.assertIn("Start Box", svg_str)
        self.assertIn("Decision", svg_str)
        self.assertIn("Outcome", svg_str)
        self.assertIn("Process", svg_str)
        self.assertIn("Evaluate", svg_str)

    def test_render_code_block_svg(self):
        """Code blocks are rendered in SVG with title, window dots, and formatted code text."""
        service = SceneService()
        service.add_code_block(
            code="def add(a, b):\n    return a + b",
            language="python",
            x=100,
            y=100,
            title="Calculator",
            theme="dark",
        )
        doc, _ = service.state.snapshot()
        svg_str, w, h = render_scene_svg(doc, padding=30)

        root = ET.fromstring(svg_str)
        self.assertIn("Calculator", svg_str)
        self.assertIn("def", svg_str)
        self.assertIn("return", svg_str)

    def test_render_svg_sanitizes_injected_color_attributes(self):
        """render_scene_svg sanitizes malicious color attributes to prevent XML breakout / XSS."""
        malicious_doc = {
            "type": "excalidraw",
            "version": 2,
            "source": "https://excalidraw.com",
            "elements": [
                {
                    "id": "exploit-1",
                    "type": "rectangle",
                    "x": 10,
                    "y": 10,
                    "width": 100,
                    "height": 50,
                    "strokeColor": 'red"><script xmlns="http://www.w3.org/1999/xhtml">alert(1)</script><rect a="',
                    "backgroundColor": 'blue" onclick="alert(2)" data="',
                    "strokeWidth": 1,
                    "roughness": 0,
                    "opacity": 100,
                }
            ],
            "appState": {
                "viewBackgroundColor": 'white"><script>alert(3)</script><g a="',
            },
        }
        svg_str, _, _ = render_scene_svg(malicious_doc)
        self.assertNotIn("<script", svg_str)
        self.assertNotIn('onclick="', svg_str)
        # Must parse as clean XML
        root = ET.fromstring(svg_str)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")


class SvgExportServiceTests(unittest.TestCase):
    def test_export_svg_creates_file_and_protects_overwrite(self):
        """export_svg writes an SVG file to disk and honors overwrite flag."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            service = SceneService()
            service.add_shape("rectangle", 10, 10, 100, 50, label="Service Box")

            # First export succeeds
            res = service.export_svg(name="arch_diagram", directory=tmp_dir, overwrite=False)
            self.assertEqual(res["status"], "svg exported")
            target_path = Path(res["path"])
            self.assertTrue(target_path.is_file())
            content = target_path.read_text(encoding="utf-8")
            ET.fromstring(content)  # Must be valid XML

            # Overwrite=False raises SceneError
            with self.assertRaises(SceneError) as cm:
                service.export_svg(name="arch_diagram", directory=tmp_dir, overwrite=False)
            self.assertIn("already exists", str(cm.exception))

            # Overwrite=True succeeds
            res2 = service.export_svg(name="arch_diagram", directory=tmp_dir, overwrite=True)
            self.assertEqual(res2["status"], "svg exported")

    def test_export_svg_directory_confinement(self):
        """export_svg rejects target directories outside allowed locations."""
        service = SceneService()
        with self.assertRaises(SceneError) as cm:
            service.export_svg(name="traversal", directory="/etc/unauthorized")
        self.assertIn("outside permitted", str(cm.exception))


class SvgExportMcpToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_svg_via_mcp_client(self):
        """MCP client can invoke export_svg tool on full server profile."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            server = create_server(toolset="full")
            async with Client(server) as client:
                # Add shape
                await client.call_tool(
                    "create_shape",
                    {"type": "rectangle", "x": 0, "y": 0, "w": 100, "h": 60, "label": "Client Node"},
                )

                # Export SVG
                res = await client.call_tool(
                    "export_svg",
                    {"name": "mcp_exported_scene", "directory": tmp_dir, "overwrite": True},
                )
                self.assertFalse(res.is_error)
                data = json.loads(res.content[0].text)
                self.assertEqual(data["status"], "svg exported")
                out_path = Path(data["path"])
                self.assertTrue(out_path.is_file())
                self.assertTrue(out_path.name.endswith(".svg"))
                content = out_path.read_text(encoding="utf-8")
                root = ET.fromstring(content)
                self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")


if __name__ == "__main__":
    unittest.main()
