import errno
import importlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from excalidraw_mcp import config
from excalidraw_mcp import scene as storage
from excalidraw_mcp.elements import rect
from excalidraw_mcp.errors import SceneError


class StorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "scenes"
        env = patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": str(self.root)})
        env.start()
        self.addCleanup(env.stop)
        self.document = storage.new_document([rect(0, 0, 100, 100)])

    def test_import_and_missing_load_do_not_create_directory(self):
        importlib.reload(storage)
        with self.assertRaisesRegex(SceneError, "not found"):
            storage.load_scene("missing")
        self.assertFalse(self.root.exists())

    def test_default_directory_is_independent_of_working_directory(self):
        fake_home = (
            Path("C:/Users/tester")
            if config.sys.platform.startswith("win")
            else Path("/home/tester")
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(config.Path, "home", return_value=fake_home),
        ):
            if config.sys.platform == "darwin":
                expected = fake_home / "Library" / "Application Support"
            elif config.sys.platform.startswith("win"):
                expected = fake_home / "AppData" / "Roaming"
            else:
                expected = fake_home / ".local" / "share"
            self.assertEqual(
                config.scene_directory(), expected / "excalidraw-mcp/scenes"
            )

    @unittest.skipIf(
        config.sys.platform in ("darwin", "win32") or config.sys.platform.startswith("win"),
        "XDG data directories are not used on macOS or Windows",
    )
    def test_xdg_data_home_must_be_absolute(self):
        with patch.dict(os.environ, {"XDG_DATA_HOME": "relative"}, clear=True):
            with self.assertRaisesRegex(
                ValueError, "XDG_DATA_HOME must be an absolute path"
            ):
                config.scene_directory()

    @unittest.skipUnless(
        config.sys.platform.startswith("win"),
        "APPDATA environment variable is checked on Windows",
    )
    def test_appdata_must_be_absolute(self):
        with patch.dict(os.environ, {"APPDATA": "relative"}, clear=True):
            with self.assertRaisesRegex(
                ValueError, "APPDATA must be an absolute path"
            ):
                config.scene_directory()

    def test_relative_configuration_rejected(self):
        with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": "relative"}):
            with self.assertRaisesRegex(ValueError, "absolute"):
                storage.save_scene("scene", self.document)

    def test_names_cannot_escape_storage(self):
        for name in (
            "../outside",
            str(self.base / "outside"),
            "a/b",
            "a\\b",
            "",
            ".",
            "a.excalidraw",
            "a\x00b",
            "x" * 129,
        ):
            with self.subTest(name=name):
                for operation in (
                    lambda: storage.save_scene(name, self.document),
                    lambda: storage.load_scene(name),
                ):
                    with self.assertRaises(SceneError):
                        operation()
        self.assertFalse(self.root.exists())

    def test_full_document_roundtrip(self):
        self.document["appState"] = {"viewBackgroundColor": "#123456"}
        self.document["files"] = {
            "asset": {
                "id": "asset",
                "mimeType": "image/png",
                "created": 0,
                "dataURL": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5s8AAAAASUVORK5CYII=",
            }
        }
        self.document["elements"].append(
            {
                "id": "image",
                "type": "image",
                "x": 0,
                "y": 0,
                "width": 1,
                "height": 1,
                "fileId": "asset",
            }
        )
        self.document["custom"] = {"label": "日本語 café"}
        target = storage.save_scene("my_scene-1", self.document)
        self.assertEqual(Path(target), self.root / "my_scene-1.excalidraw")
        self.assertEqual(storage.load_scene("my_scene-1"), self.document)
        self.assertIn("日本語", Path(target).read_text(encoding="utf-8"))

    def test_overwrite_requires_explicit_opt_in(self):
        storage.save_scene("existing", self.document)
        replacement = storage.new_document()
        with self.assertRaisesRegex(SceneError, "overwrite=true"):
            storage.save_scene("existing", replacement)
        self.assertEqual(storage.load_scene("existing"), self.document)
        storage.save_scene("existing", replacement, overwrite=True)
        self.assertEqual(storage.load_scene("existing"), replacement)

    def test_symlinks_are_rejected_for_reads_and_writes(self):
        self.root.mkdir()
        outside = self.base / "outside.excalidraw"
        outside.write_text(json.dumps(self.document), encoding="utf-8")
        link = self.root / "linked.excalidraw"
        link.symlink_to(outside)
        for operation in (
            lambda: storage.load_scene("linked"),
            lambda: storage.save_scene(
                "linked", storage.new_document(), overwrite=True
            ),
        ):
            with self.assertRaisesRegex(SceneError, "symlink"):
                operation()
        self.assertEqual(json.loads(outside.read_text()), self.document)
        self.assertTrue(link.is_symlink())

    def test_dangling_symlink_and_directory_rejected(self):
        self.root.mkdir()
        (self.root / "dangling.excalidraw").symlink_to(self.base / "absent")
        (self.root / "directory.excalidraw").mkdir()
        for name in ("dangling", "directory"):
            with self.subTest(name=name):
                with self.assertRaises(SceneError):
                    storage.save_scene(name, self.document, overwrite=True)
                with self.assertRaises(SceneError):
                    storage.load_scene(name)

    def test_failed_flush_or_replace_preserves_previous_file(self):
        storage.save_scene("existing", self.document)
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with patch.object(
                    storage.os,
                    operation,
                    side_effect=OSError(errno.ENOSPC, "disk full"),
                ):
                    with self.assertRaisesRegex(SceneError, "disk full"):
                        storage.save_scene(
                            "existing", storage.new_document(), overwrite=True
                        )
                self.assertEqual(storage.load_scene("existing"), self.document)
                self.assertEqual(
                    list(self.root.iterdir()), [self.root / "existing.excalidraw"]
                )

    def test_concurrent_no_overwrite_saves_have_one_winner(self):
        def save():
            try:
                storage.save_scene("race", self.document)
                return True
            except SceneError:
                return False

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: save(), range(4)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(storage.load_scene("race"), self.document)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_invalid_documents_rejected(self):
        invalid = [
            [],
            {},
            {**self.document, "version": True},
            {**self.document, "elements": [{}]},
            {**self.document, "elements": self.document["elements"] * 2},
            {**self.document, "appState": []},
            {**self.document, "files": []},
            {**self.document, "extra": float("nan")},
        ]
        for document in invalid:
            with self.subTest(document=document):
                with self.assertRaises(SceneError):
                    storage.save_scene("bad", document)
        self.assertFalse(self.root.exists())

    def test_invalid_json_and_encoding_are_actionable(self):
        self.root.mkdir()
        target = self.root / "bad.excalidraw"
        for payload in (b"{", b"\xff"):
            target.write_bytes(payload)
            with self.assertRaisesRegex(SceneError, "UTF-8 JSON"):
                storage.load_scene("bad")

    def test_unencodable_text_preserves_existing_file(self):
        storage.save_scene("existing", self.document)
        invalid = {**self.document, "custom": "\ud800"}
        with self.assertRaisesRegex(SceneError, "UTF-8"):
            storage.save_scene("existing", invalid, overwrite=True)
        self.assertEqual(storage.load_scene("existing"), self.document)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_extreme_coordinates_are_rejected(self):
        self.document["elements"][0]["x"] = 10**1000
        with self.assertRaisesRegex(SceneError, "finite x"):
            storage.save_scene("bad", self.document)


if __name__ == "__main__":
    unittest.main()
