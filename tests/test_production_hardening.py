import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from excalidraw_mcp import config
from excalidraw_mcp import server as main
from excalidraw_mcp.elements import rect
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document, validate_document
from excalidraw_mcp.scene import load_scene, save_scene


class ConfigurationLimitTests(unittest.TestCase):
    def test_limit_defaults_are_bounded(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.max_scene_bytes(), 25 * 1024 * 1024)
            self.assertEqual(config.max_export_bytes(), 25 * 1024 * 1024)
            self.assertEqual(config.max_history_bytes(), 100 * 1024 * 1024)
            self.assertEqual(config.max_elements(), 10_000)

    def test_limit_configuration_rejects_invalid_values(self):
        cases = (
            ("EXCALIDRAW_MAX_SCENE_BYTES", "not-a-number", "integer"),
            ("EXCALIDRAW_MAX_SCENE_BYTES", "1023", "between"),
            ("EXCALIDRAW_MAX_ELEMENTS", "0", "between"),
            ("EXCALIDRAW_MAX_ELEMENTS", "100001", "between"),
        )
        for name, value, message in cases:
            with (
                self.subTest(name=name, value=value),
                patch.dict(os.environ, {name: value}, clear=True),
            ):
                with self.assertRaisesRegex(ValueError, message):
                    config.max_scene_bytes() if "BYTES" in name else config.max_elements()

    def test_document_element_limit_is_enforced(self):
        document = new_document([rect(0, 0, 10, 10), rect(20, 0, 10, 10)])
        with patch.dict(os.environ, {"EXCALIDRAW_MAX_ELEMENTS": "1"}, clear=True):
            with self.assertRaisesRegex(SceneError, "limit of 1 elements"):
                validate_document(document)


class StorageLimitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "scenes"

    def test_oversized_scene_is_not_saved(self):
        document = new_document()
        document["metadata"] = "x" * 2_000
        with patch.dict(
            os.environ,
            {
                "EXCALIDRAW_SCENE_DIR": str(self.root),
                "EXCALIDRAW_MAX_SCENE_BYTES": "1024",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(SceneError, "limit of 1024 bytes"):
                save_scene("large", document)
        self.assertFalse(self.root.exists())

    def test_oversized_scene_is_rejected_before_json_parsing(self):
        self.root.mkdir()
        (self.root / "large.excalidraw").write_bytes(b"{" + b" " * 1_024)
        with patch.dict(
            os.environ,
            {
                "EXCALIDRAW_SCENE_DIR": str(self.root),
                "EXCALIDRAW_MAX_SCENE_BYTES": "1024",
            },
            clear=True,
        ):
            with self.assertRaisesRegex(SceneError, "limit of 1024 bytes"):
                load_scene("large")


class EntrypointTests(unittest.TestCase):
    def test_main_entrypoint_runs_mcp_run(self):
        with patch.object(main.mcp, "run") as run:
            main.main()
        run.assert_called_once_with(show_banner=False)

    def test_console_entrypoint_runs_stdio_without_banner(self):
        with patch.object(main.mcp, "run") as run:
            main.run()
        run.assert_called_once_with(show_banner=False)


if __name__ == "__main__":
    unittest.main()
