import asyncio
import json
import os
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from excalidraw_mcp.document import MIME_TYPE, normalize_document, serialize_document
from excalidraw_mcp.elements import arrow, bind_text, diamond, ellipse, rect, text
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document
from excalidraw_mcp.scene import load_scene
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.state import SceneState
from excalidraw_mcp.server import create_server

FIXTURES = Path(__file__).parent / "fixtures" / "excalidraw"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5s8AAAAASUVORK5CYII="


class DocumentTests(unittest.TestCase):
    def test_generated_elements_have_explicit_common_fields(self):
        elements = [
            rect(0, 0, 100, 80),
            ellipse(120, 0, 100, 100),
            diamond(250, 0, 100, 100),
            text(0, 150, "Hello"),
            arrow(0, 250, 100, 300),
        ]
        required = {
            "id",
            "type",
            "x",
            "y",
            "width",
            "height",
            "angle",
            "seed",
            "version",
            "versionNonce",
            "updated",
            "isDeleted",
            "groupIds",
            "frameId",
            "boundElements",
            "roundness",
            "link",
            "locked",
            "index",
        }
        for el in elements:
            self.assertTrue(required <= el.keys(), el["type"])
        document = new_document(elements)
        self.assertEqual(normalize_document(document), document)

    def test_multiline_text_and_bound_alignment(self):
        label = text(25, 25, "API\n日本語", fontSize=20)
        self.assertEqual(label["height"], 50)
        self.assertEqual(label["width"], 36)
        self.assertEqual(label["originalText"], "API\n日本語")
        self.assertEqual(label["fontFamily"], 2)
        container = rect(0, 0, 100, 100)
        bind_text(label, container)
        self.assertEqual(label["textAlign"], "center")
        self.assertEqual(label["verticalAlign"], "middle")

    def test_arrow_geometry_all_directions_and_zero_length(self):
        for x2, y2 in ((100, 50), (-100, 50), (100, -50), (-100, -50), (0, 0)):
            with self.subTest(end=(x2, y2)):
                el = arrow(0, 0, x2, y2)
                restored = normalize_document(new_document([el]))["elements"][0]
                self.assertEqual(restored["width"], abs(x2))
                self.assertEqual(restored["height"], abs(y2))
                self.assertEqual(restored["points"][-1], [x2, y2])
                self.assertIsNone(restored["startArrowhead"])
                self.assertEqual(restored["endArrowhead"], "arrow")

    def test_legacy_arrow_origin_normalization_preserves_world_points(self):
        el = {
            "id": "arrow",
            "type": "arrow",
            "x": 10,
            "y": 20,
            "points": [[5, 8], [-10, 20], [35, -10]],
        }
        before = deepcopy(el)
        result = normalize_document(new_document([el]))["elements"][0]
        self.assertEqual(result["points"][0], [0, 0])
        self.assertEqual(
            [
                result["x"] + result["points"][2][0],
                result["y"] + result["points"][2][1],
            ],
            [45, 10],
        )
        self.assertEqual((result["width"], result["height"]), (45, 30))
        self.assertEqual(el, before)

    def test_rotated_arrow_pivot_is_preserved(self):
        el = arrow(10, 20, 100, 200)
        el.update(angle=0.5, points=[[10, 10], [90, 180]])
        self.assertEqual(normalize_document(new_document([el]))["elements"][0], el)

    def test_upstream_export_roundtrip_preserves_existing_fields(self):
        original = json.loads(
            (FIXTURES / "upstream-legacy-text.excalidraw").read_text()
        )
        normalized = normalize_document(original)
        for key, value in original["elements"][0].items():
            self.assertEqual(normalized["elements"][0][key], value, key)
        self.assertEqual(normalized["appState"], original["appState"])
        self.assertEqual(normalized["elements"][0]["lineHeight"], 57 / 36)
        self.assertEqual(normalize_document(normalized), normalized)
        self.assertEqual(json.loads(serialize_document(original)), normalized)

    def test_bindings_are_preserved_and_legacy_fields_filled(self):
        service = SceneService()
        service.draw_architecture("box: API, box: DB")
        document = json.loads(service.export_scene())
        connector = next(el for el in document["elements"] if el["type"] == "arrow")
        for field in ("startBinding", "endBinding"):
            binding = connector[field]
            self.assertEqual((binding["focus"], binding["gap"]), (0, 0))
            self.assertEqual(binding["fixedPoint"], [0.5, 0.5])
            target = next(
                el for el in document["elements"] if el["id"] == binding["elementId"]
            )
            self.assertIn(
                {"id": connector["id"], "type": "arrow"}, target["boundElements"]
            )

    def test_image_assets_unknown_elements_and_metadata_survive(self):
        document = new_document(
            [
                {
                    "id": "image",
                    "type": "image",
                    "x": 0,
                    "y": 0,
                    "width": 1,
                    "height": 1,
                    "fileId": "asset",
                    "scale": [1, 1],
                    "status": "saved",
                },
                {
                    "id": "future",
                    "type": "future-shape",
                    "x": 10,
                    "y": 20,
                    "custom": [1, 2],
                },
            ]
        )
        document["files"] = {
            "asset": {
                "id": "asset",
                "mimeType": "image/png",
                "created": 1,
                "dataURL": "data:image/png;base64," + PNG,
            }
        }
        document["appState"] = {"viewBackgroundColor": "#123456", "custom": "preserved"}
        document["extra"] = {"label": "café 日本語"}
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": directory}),
        ):
            state = SceneState()
            state.replace(document)
            service = SceneService(state)
            service.save("original")
            service.clear()
            service.load("original")
            service.save("copy")
            self.assertEqual(load_scene("copy"), document)
            self.assertEqual(json.loads(service.export_scene()), document)

    def test_missing_or_invalid_referenced_asset_is_rejected(self):
        document = new_document(
            [{"id": "image", "type": "image", "x": 0, "y": 0, "fileId": "asset"}]
        )
        asset = {
            "id": "asset",
            "created": 1,
            "mimeType": "image/png",
            "dataURL": "data:image/png;base64," + PNG,
        }
        for replacement in (
            None,
            {},
            {**asset, "dataURL": "https://example.com/image.png"},
            {**asset, "dataURL": "data:image/png;base64,invalid!"},
            {**asset, "id": "mismatch"},
        ):
            with self.subTest(asset=replacement):
                document["files"] = (
                    {} if replacement is None else {"asset": replacement}
                )
                with self.assertRaises(SceneError):
                    normalize_document(document)

    def test_malformed_supported_elements_do_not_replace_state(self):
        state = SceneState()
        state.add(rect(0, 0, 100, 100))
        before = state.document()
        malformed = [
            {**text(0, 0, "text"), "fontSize": 0},
            {**text(0, 0, "text"), "lineHeight": -1},
            {**arrow(0, 0, 10, 10), "points": [[0, 0], [float("nan"), 1]]},
            {**rect(0, 0, 100, 100), "opacity": 101},
            {**rect(0, 0, 100, 100), "version": "invalid"},
            {**rect(0, 0, 100, 100), "groupIds": {}},
            {**rect(0, 0, 100, 100), "isDeleted": "false"},
            {**text(0, 0, "text"), "originalText": []},
            {"id": "shape", "type": "rectangle", "x": 0, "y": 0},
        ]
        for el in malformed:
            with self.subTest(element=el):
                with self.assertRaises(SceneError):
                    state.replace(new_document([el]))
                self.assertEqual(state.document(), before)

    def test_export_tool_returns_self_contained_document_without_writes(self):
        service = SceneService()
        service.add_shape("rectangle", 0, 0, 100, 100, "API")
        before, revision = service.state.document(), service.state.revision
        tools = {
            tool.name: tool.fn
            for tool in asyncio.run(create_server(service).list_tools())
        }
        with patch(
            "excalidraw_mcp.service.save_scene",
            side_effect=AssertionError("unexpected save"),
        ):
            result = tools["scene_storage"](action="export")
        self.assertEqual(result.type, "resource")
        self.assertEqual(result.resource.mimeType, MIME_TYPE)
        self.assertTrue(str(result.resource.uri).endswith(".excalidraw"))
        self.assertEqual(json.loads(result.resource.text), before)
        self.assertEqual(service.state.revision, revision)
        # It must also be an ordinary MCP content object, not a JSON-string wrapper.
        self.assertEqual(
            result.model_dump(mode="json")["resource"]["text"], service.export_scene()
        )

    def test_empty_export_is_a_valid_document(self):
        self.assertEqual(json.loads(SceneService().export_scene()), new_document())

    def test_file_save_and_client_export_use_identical_serialization(self):
        service = SceneService()
        service.draw_architecture("box: API, diamond: Decision")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": directory}),
        ):
            path = service.save("diagram")["path"]
            self.assertEqual(
                Path(path).read_text(encoding="utf-8"), service.export_scene()
            )

    def test_embedded_export_is_an_immutable_identifiable_snapshot(self):
        service = SceneService()
        result = service.add_shape("rectangle", 0, 0, 100, 100)
        tools = {
            tool.name: tool.fn
            for tool in asyncio.run(create_server(service).list_tools())
        }
        first = tools["scene_storage"](action="export")
        self.assertEqual(first.resource.uri, tools["scene_storage"](action="export").resource.uri)
        service.move(result["rectangle_id"], 10, 20)
        second = tools["scene_storage"](action="export")
        self.assertNotEqual(first.resource.uri, second.resource.uri)
        self.assertEqual(json.loads(first.resource.text)["elements"][0]["x"], 0)
        self.assertEqual(json.loads(second.resource.text)["elements"][0]["x"], 10)


if __name__ == "__main__":
    unittest.main()
