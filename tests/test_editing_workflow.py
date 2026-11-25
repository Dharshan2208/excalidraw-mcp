import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.state import SceneState


class EditingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.state = SceneState(max_history=3)
        self.service = SceneService(self.state)

    def test_inspect_paginate_and_get(self):
        ids = [self.service.add_text(i, 0, str(i))["text_id"] for i in range(4)]
        page = self.service.get_scene(offset=1, limit=2)
        self.assertEqual((page["total"], page["has_more"]), (4, True))
        self.assertEqual([el["id"] for el in page["elements"]], ids[1:3])
        self.assertEqual(self.service.get_element(ids[2])["element"]["text"], "2")
        with self.assertRaises(SceneError):
            self.service.get_scene(limit=201)

    def test_update_label_styles_and_remove_label(self):
        result = self.service.add_shape("rectangle", 0, 0, 100, 100)
        updated = self.service.update_element(
            result["rectangle_id"], label="API", background_color="#ffeeaa", opacity=50
        )
        self.assertIsNotNone(updated["label_id"])
        shape = self.state.get(result["rectangle_id"])
        label = self.state.get(updated["label_id"])
        self.assertEqual((shape["backgroundColor"], shape["opacity"]), ("#ffeeaa", 50))
        self.assertEqual(
            (label["x"] + label["width"] / 2, label["y"] + label["height"] / 2),
            (50, 50),
        )
        removed = self.service.update_element(result["rectangle_id"], label="")
        self.assertIsNone(removed["label_id"])
        self.assertIsNone(self.state.get(updated["label_id"]))

    def test_resize_recenters_label_and_reroutes_connector(self):
        a = self.service.add_shape("rectangle", 0, 0, 100, 100, "A")
        b = self.service.add_shape("rectangle", 300, 0, 100, 100, "B")
        edge = self.service.connect(a["rectangle_id"], b["rectangle_id"], "request")
        self.service.resize(a["rectangle_id"], 200, 160)
        shape, label = self.state.get(a["rectangle_id"]), self.state.get(a["label_id"])
        self.assertEqual(
            (label["x"] + label["width"] / 2, label["y"] + label["height"] / 2),
            (100, 80),
        )
        connector = self.state.get(edge["arrow_id"])
        self.assertEqual((connector["x"], connector["y"]), (200, 68))
        self.assertEqual(connector["startBinding"]["elementId"], a["rectangle_id"])

    def test_connect_rejects_invalid_targets_without_partial_change(self):
        shape = self.service.add_shape("rectangle", 0, 0, 100, 100)
        standalone = self.service.add_text(200, 0, "text")
        before = self.state.document()
        with self.assertRaises(SceneError):
            self.service.connect(shape["rectangle_id"], standalone["text_id"])
        self.assertEqual(self.state.document(), before)

    def test_undo_is_bounded_and_failed_or_read_operations_add_no_history(self):
        ids = []
        for i in range(5):
            ids.append(self.service.add_text(i, 0, str(i))["text_id"])
        self.assertEqual(self.state.history_depth, 3)
        before = self.state.history_depth
        self.service.get_scene()
        with self.assertRaises(SceneError):
            self.service.delete("missing")
        self.assertEqual(self.state.history_depth, before)
        for remaining in (4, 3, 2):
            self.service.undo()
            self.assertEqual(len(self.state.all()), remaining)
        with self.assertRaisesRegex(SceneError, "Nothing"):
            self.service.undo()

    def test_saved_scene_listing_and_read_do_not_change_active_scene(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": directory}),
        ):
            self.service.add_text(0, 0, "one")
            self.service.save("zeta")
            self.service.save("alpha")
            before, revision = self.state.document(), self.state.revision
            self.assertEqual(
                self.service.list_saved_scenes()["scenes"], ["alpha", "zeta"]
            )
            self.assertEqual(json.loads(self.service.read_saved_scene("alpha")), before)
            self.assertEqual(self.state.revision, revision)

    def test_draw_architecture_is_single_undo_step(self):
        self.service.draw_architecture("box: API, box: DB")
        self.assertEqual(self.state.revision, 1)
        self.service.undo()
        self.assertEqual(self.state.all(), [])

    def test_move_grouped_bound_label_is_not_double_translated(self):
        r1 = self.service.add_shape("rectangle", 100, 100, 120, 80, label="Node")
        self.service.group_elements([r1["rectangle_id"], r1["label_id"]])
        before_lbl = self.state.get(r1["label_id"])
        self.service.move(r1["rectangle_id"], 200, 250)
        after_lbl = self.state.get(r1["label_id"])
        self.assertAlmostEqual(after_lbl["x"] - before_lbl["x"], 100.0)
        self.assertAlmostEqual(after_lbl["y"] - before_lbl["y"], 150.0)

    def test_add_shape_and_text_validate_frame_id(self):
        with self.assertRaises(SceneError):
            self.service.add_shape("rectangle", 0, 0, 100, 100, frame_id="missing-frame")
        with self.assertRaises(SceneError):
            self.service.add_text(0, 0, "hello", frame_id="missing-frame")

    def test_update_element_clears_stale_custom_font_family_on_container(self):
        r = self.service.add_shape("rectangle", 0, 0, 140, 80, label="Hello", font_family="JetBrains Mono")
        self.service.update_element(r["rectangle_id"], font_family="sans-serif")
        lbl = self.state.get(r["label_id"])
        self.assertEqual(lbl["fontFamily"], 2)
        self.assertNotIn("fontFamily", lbl.get("customData") or {})


if __name__ == "__main__":
    unittest.main()
