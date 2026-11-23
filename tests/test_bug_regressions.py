import asyncio
import json
import math
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastmcp import Client

from excalidraw_mcp.document import normalize_document
from excalidraw_mcp.elements import rect
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document
from excalidraw_mcp.scene import list_scenes, save_scene
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.state import SceneState
from excalidraw_mcp.layout import boundary_point
from excalidraw_mcp.server import create_server


class CompatibilityAndStateRegressionTests(unittest.TestCase):
    def test_unknown_relationship_fields_survive_normalization(self):
        future = {
            "id": "future",
            "type": "future-shape",
            "x": 0,
            "y": 0,
            "containerId": "future-container",
            "boundElements": [{"id": "other", "type": "future-link"}],
        }
        container = {
            "id": "future-container",
            "type": "future-container",
            "x": 1,
            "y": 1,
        }
        other = {"id": "other", "type": "future-link", "x": 2, "y": 2}
        result = normalize_document(new_document([future, container, other]))
        self.assertEqual(result["elements"][0], future)

    def test_failed_undo_does_not_consume_history(self):
        state = SceneState(max_history=5)
        for x in (0, 20, 40):
            state.add(rect(x, 0, 10, 10))
        before = state.document(), state.revision, state.history_depth
        with patch.dict(os.environ, {"EXCALIDRAW_MAX_ELEMENTS": "1"}):
            with self.assertRaises(SceneError):
                state.undo()
        self.assertEqual(
            (state.document(), state.revision, state.history_depth), before
        )

    def test_inspection_uses_one_atomic_snapshot(self):
        state = SceneState()
        service = SceneService(state)
        service.add_text(0, 0, "one")
        document = state.document()
        with patch.object(state, "snapshot", return_value=(document, 42)), patch.object(
            state, "all", side_effect=AssertionError("split read")
        ):
            result = service.get_scene()
        self.assertEqual((result["revision"], result["total"]), (42, 1))


class ContractRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_rejects_coerced_numbers_and_invalid_colors(self):
        async with Client(create_server(), timeout=5) as client:
            cases = (
                {"x": True, "y": 0, "w": 10, "h": 10},
                {"x": "1", "y": 0, "w": 10, "h": 10},
                {
                    "x": 0,
                    "y": 0,
                    "w": 10,
                    "h": 10,
                    "strokeColor": "not-a-color",
                },
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    result = await client.call_tool(
                        "add_rectangle", arguments, raise_on_error=False
                    )
                    self.assertTrue(result.is_error)
            invalid_overwrite = await client.call_tool(
                "save", {"name": "scene", "overwrite": "false"}, raise_on_error=False
            )
            self.assertTrue(invalid_overwrite.is_error)

    async def test_destructive_and_idempotent_annotations_match_behavior(self):
        tools = {tool.name: tool for tool in await create_server().list_tools()}
        self.assertTrue(tools["delete"].annotations.destructiveHint)
        self.assertTrue(tools["update_element"].annotations.idempotentHint)


class StorageAndLimitRegressionTests(unittest.TestCase):
    def test_listing_skips_unloadable_and_unsafe_entries(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"EXCALIDRAW_SCENE_DIR": directory}
        ):
            root = Path(directory)
            save_scene("valid", new_document())
            (root / "bad name.excalidraw").write_text("{}", encoding="utf-8")
            (root / ".excalidraw").write_text("{}", encoding="utf-8")
            (root / "directory.excalidraw").mkdir()
            (root / "link.excalidraw").symlink_to(root / "valid.excalidraw")
            self.assertEqual(list_scenes(), ["valid"])

    @unittest.skipIf(
        sys.platform == "win32", "POSIX file permission mode bits are not enforced on Windows"
    )
    def test_new_scene_directory_is_private(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"EXCALIDRAW_SCENE_DIR": str(Path(directory) / "scenes")}
        ):
            save_scene("private", new_document())
            mode = stat.S_IMODE((Path(directory) / "scenes").stat().st_mode)
            self.assertEqual(mode & 0o077, 0)

    def test_export_limit_is_enforced(self):
        service = SceneService()
        service.add_text(0, 0, "x" * 2_000)
        with patch.dict(os.environ, {"EXCALIDRAW_MAX_EXPORT_BYTES": "1024"}):
            with self.assertRaisesRegex(SceneError, "Export exceeds"):
                service.export_scene()

    def test_history_has_a_total_byte_budget(self):
        state = SceneState(max_history=100, max_history_size=1_024)
        service = SceneService(state)
        for index in range(20):
            service.add_text(index, 0, "x" * 100)
        self.assertLessEqual(state._history_bytes, 1_024)


class GeometryAndGraphRegressionTests(unittest.TestCase):
    def test_coincident_shapes_get_nonzero_connector(self):
        service = SceneService()
        first = service.add_shape("rectangle", 0, 0, 100, 100)["rectangle_id"]
        second = service.add_shape("rectangle", 0, 0, 100, 100)["rectangle_id"]
        connector_id = service.connect(first, second)["arrow_id"]
        connector = service.state.get(connector_id)
        self.assertNotEqual(connector["points"][0], connector["points"][-1])
        self.assertGreater(connector["width"], 0)

    def test_boundary_point_accounts_for_rotation_and_diamond_edges(self):
        rotated = {
            "shape": "rectangle",
            "x": 0,
            "y": 0,
            "w": 100,
            "h": 50,
            "angle": math.pi / 2,
        }
        target = {"shape": "rectangle", "x": 200, "y": 20, "w": 10, "h": 10}
        x, y = boundary_point(rotated, target)
        self.assertAlmostEqual(x, 75)
        self.assertAlmostEqual(y, 25)
        diamond = {"shape": "diamond", "x": 0, "y": 0, "w": 100, "h": 100}
        x, y = boundary_point(
            diamond, {"shape": "rectangle", "x": 100, "y": 100, "w": 1, "h": 1}
        )
        self.assertAlmostEqual(abs(x - 50) + abs(y - 50), 50)

    def test_graph_rejects_blank_fields_and_invalid_direction(self):
        service = SceneService()
        for nodes, direction in (
            ([{"id": " ", "label": "A"}], "horizontal"),
            ([{"id": "a", "label": "   "}], "horizontal"),
            ([{"id": "a", "label": "A"}], "diagonal"),
        ):
            with self.subTest(nodes=nodes, direction=direction):
                with self.assertRaises(SceneError):
                    service.draw_graph(nodes, [], direction=direction)

    def test_generated_edge_ids_skip_explicit_ids(self):
        service = SceneService()
        result = service.draw_graph(
            [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}],
            [
                {"id": "edge-1", "source": "a", "target": "b"},
                {"source": "b", "target": "a"},
            ],
            layout="horizontal",
        )
        self.assertEqual(set(result["edge_map"]), {"edge-1", "edge-2"})

    def test_late_label_inherits_updated_text_style(self):
        service = SceneService()
        shape = service.add_shape(
            "rectangle", 0, 0, 100, 100, strokeColor="#ff0000"
        )
        result = service.update_element(
            shape["rectangle_id"], label="API", stroke_color="#00ff00", opacity=60
        )
        label = service.state.get(result["label_id"])
        self.assertEqual((label["strokeColor"], label["opacity"]), ("#00ff00", 60))
        service.update_element(shape["rectangle_id"], label="")
        service.update_element(shape["rectangle_id"], label="")


if __name__ == "__main__":
    unittest.main()
