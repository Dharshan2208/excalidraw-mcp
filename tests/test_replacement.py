import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastmcp.exceptions import ToolError

from excalidraw_mcp import server as main
from excalidraw_mcp.elements import rect
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.scene import new_document
from excalidraw_mcp.state import SceneState
from excalidraw_mcp.service import SceneService
from excalidraw_mcp import service as service_module


class ReplacementTests(unittest.TestCase):
    def setUp(self):
        self.scene = SceneState()
        self.original = new_document([rect(0, 0, 100, 100)])
        self.original["appState"] = {"viewBackgroundColor": "#123456"}
        self.original["files"] = {"asset": {"dataURL": "data:image/png;base64,example"}}
        self.original["custom"] = "preserve me"
        self.scene.replace(self.original)
        server = main.create_server(SceneService(self.scene))
        self.tools = SimpleNamespace(
            **{tool.name: tool.fn for tool in asyncio.run(server.list_tools())}
        )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        env = patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": str(self.root)})
        env.start()
        self.addCleanup(env.stop)

    def test_blank_architecture_keeps_current_document(self):
        for prompt in ("", " \n, ", "box:", "-*", "box: API, circle:"):
            with self.subTest(prompt=prompt):
                with self.assertRaises(ToolError):
                    self.tools.generate_diagram(format="architecture", prompt=prompt)
                self.assertEqual(self.scene.document(), self.original)

    def test_construction_failure_keeps_current_document(self):
        with patch.object(
            service_module, "text", side_effect=RuntimeError("construction failed")
        ):
            with self.assertRaises(RuntimeError):
                self.tools.generate_diagram(format="architecture", prompt="box: API, box: Database")
        self.assertEqual(self.scene.document(), self.original)

    def test_failed_load_keeps_current_document(self):
        for document in (
            {**self.original, "elements": [self.original["elements"][0], {}]},
            {**self.original, "elements": None},
            {"unrelated": "JSON"},
        ):
            (self.root / "bad.excalidraw").write_text(
                json.dumps(document), encoding="utf-8"
            )
            with self.assertRaises(ToolError):
                self.tools.load("bad")
            self.assertEqual(self.scene.document(), self.original)
        with self.assertRaises(ToolError):
            self.tools.load("absent")
        self.assertEqual(self.scene.document(), self.original)

    def test_tool_roundtrip_preserves_metadata_and_assets(self):
        result = self.tools.save("roundtrip")
        self.assertTrue(Path(result["path"]).is_absolute())
        self.scene.clear()
        self.tools.load("roundtrip")
        self.tools.update_element(self.original["elements"][0]["id"], x=10, y=20)
        self.tools.save("roundtrip", overwrite=True)
        document = json.loads((self.root / "roundtrip.excalidraw").read_text())
        self.assertEqual(document["files"], self.original["files"])
        self.assertEqual(document["appState"], self.original["appState"])
        self.assertEqual(document["custom"], "preserve me")
        self.assertEqual(document["elements"][0]["x"], 10)

    def test_tool_save_reports_overwrite_error(self):
        self.tools.save("existing")
        with self.assertRaisesRegex(ToolError, "overwrite=true"):
            self.tools.save("existing")

    def test_successful_architecture_commits_complete_document(self):
        result = self.tools.generate_diagram(format="architecture", prompt="box: API, circle: Database")
        self.assertEqual(result["nodes"], 2)
        self.assertIsNone(result["url"])
        self.assertEqual(len(self.scene.all()), 5)
        self.assertEqual(self.scene.document()["files"], {})
        self.assertNotIn("custom", self.scene.document())

    def test_preview_renders_inline_image(self):
        result = self.tools.preview()
        self.assertIsNotNone(result)
        self.assertEqual(result._mime_type, "image/png")
        self.assertTrue(len(result._get_data()) > 0)
        self.assertEqual(self.scene.document(), self.original)

    def test_state_replacement_is_validated_and_detached(self):
        with self.assertRaises(SceneError):
            self.scene.replace(new_document([{}]))
        self.assertEqual(self.scene.document(), self.original)
        snapshot = self.scene.document()
        snapshot["appState"].clear()
        self.original["files"].clear()
        self.assertTrue(self.scene.document()["appState"])
        self.assertTrue(self.scene.document()["files"])


if __name__ == "__main__":
    unittest.main()
