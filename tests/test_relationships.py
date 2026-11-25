import unittest
from unittest.mock import patch

from excalidraw_mcp import service as service_module
from excalidraw_mcp.elements import arrow, bind_text, rect, text
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document
from excalidraw_mcp.service import SceneService


class RelationshipTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def connected_scene(self, points=None):
        a, b = rect(0, 0, 100, 100), rect(300, 0, 100, 100)
        connector = arrow(50, 50, 350, 50)
        if points is not None:
            connector["points"] = points
        connector["startBinding"] = {
            "elementId": a["id"],
            "fixedPoint": [0.5, 0.5],
            "mode": "inside",
        }
        connector["endBinding"] = {
            "elementId": b["id"],
            "fixedPoint": [0.5, 0.5],
            "mode": "inside",
        }
        label = text(200, 50, "request")
        bind_text(label, connector)
        self.state.replace(new_document([a, b, connector, label]))
        return a["id"], b["id"], connector["id"], label["id"]

    def test_shape_move_translates_label(self):
        result = self.service.add_shape("diamond", 0, 0, 100, 100, "decision")
        before = self.state.get(result["label_id"])
        self.service.move(result["diamond_id"], -20, 40)
        after = self.state.get(result["label_id"])
        self.assertEqual((after["x"], after["y"]), (before["x"] - 20, before["y"] + 40))
        with self.assertRaisesRegex(SceneError, "container"):
            self.service.move(result["label_id"], 0, 0)

    def test_delete_shape_removes_label(self):
        result = self.service.add_shape("rectangle", 0, 0, 100, 100, "A")
        self.service.delete(result["rectangle_id"])
        self.assertEqual(self.state.all(), [])

    def test_delete_label_cleans_reverse_binding_and_bumps_container(self):
        result = self.service.add_shape("ellipse", 0, 0, 100, 100, "A")
        before = self.state.get(result["circle_id"])
        self.service.delete(result["label_id"])
        after = self.state.get(result["circle_id"])
        self.assertEqual(after["boundElements"], [])
        self.assertEqual(after["version"], before["version"] + 1)

    def test_arrow_move_translates_label_and_detaches_both_ends(self):
        a, b, connector, label = self.connected_scene()
        self.service.move(connector, 100, 100)
        self.assertIsNone(self.state.get(connector)["startBinding"])
        self.assertIsNone(self.state.get(connector)["endBinding"])
        self.assertEqual(self.state.get(a)["boundElements"], [])
        self.assertEqual(self.state.get(b)["boundElements"], [])
        self.assertEqual(
            (self.state.get(label)["x"], self.state.get(label)["y"]), (250, 100)
        )

    def test_delete_shape_detaches_surviving_connector(self):
        a, b, connector, label = self.connected_scene()
        self.service.delete(a)
        after = self.state.get(connector)
        self.assertIsNone(after["startBinding"])
        self.assertEqual(after["endBinding"]["elementId"], b)
        self.assertEqual(after["points"], [[0, 0], [300, 0]])
        self.assertIsNotNone(self.state.get(label))

    def test_delete_arrow_removes_label_and_both_reverse_references(self):
        a, b, connector, label = self.connected_scene()
        self.service.delete(connector)
        self.assertIsNone(self.state.get(label))
        self.assertEqual(self.state.get(a)["boundElements"], [])
        self.assertEqual(self.state.get(b)["boundElements"], [])

    def test_shape_move_updates_only_bound_endpoint_and_label_midpoint(self):
        a, b, connector, label = self.connected_scene()
        self.service.move(a, 40, -20)
        after = self.state.get(connector)
        self.assertEqual((after["x"], after["y"]), (90, 30))
        self.assertEqual(after["points"], [[0, 0], [260, 20]])
        self.assertEqual(
            (self.state.get(label)["x"], self.state.get(label)["y"]), (220, 40)
        )
        self.assertEqual(self.state.get(b)["x"], 300)

    def test_polyline_move_preserves_intermediate_world_points(self):
        a, _, connector, _ = self.connected_scene([[0, 0], [100, -50], [300, 0]])
        self.service.move(a, 20, 30)
        after = self.state.get(connector)
        self.assertEqual(
            [after["x"] + after["points"][1][0], after["y"] + after["points"][1][1]],
            [150, 0],
        )

    def test_both_ends_on_same_shape_translate_whole_polyline(self):
        a, _, connector, label = self.connected_scene([[0, 0], [100, -50], [300, 0]])
        document = self.state.document()
        el = next(el for el in document["elements"] if el["id"] == connector)
        el["endBinding"]["elementId"] = a
        self.state.replace(document)
        self.service.move(a, 20, 30)
        after = self.state.get(connector)
        self.assertEqual((after["x"], after["y"]), (70, 80))
        self.assertEqual(after["points"], [[0, 0], [100, -50], [300, 0]])
        self.assertEqual(
            (self.state.get(label)["x"], self.state.get(label)["y"]), (220, 80)
        )

    def test_coordinate_arrow_label_has_ownership(self):
        result = self.service.add_arrow(0, 0, 100, 100, label="request")
        self.assertEqual(
            self.state.get(result["label_id"])["containerId"], result["arrow_id"]
        )
        self.service.move(result["arrow_id"], 10, 20)
        moved_label = self.state.get(result["label_id"])
        self.assertEqual(
            (
                moved_label["x"] + moved_label["width"] / 2,
                moved_label["y"] + moved_label["height"] / 2,
            ),
            (60, 70),
        )
        self.service.delete(result["arrow_id"])
        self.assertEqual(self.state.all(), [])

    def test_unsupported_connector_edit_rolls_back_whole_move(self):
        # elbowed=True is now supported via rerouting; rotated (angle != 0) remains unsupported
        for property_name, value in (("angle", 0.5),):
            a, _, connector, _ = self.connected_scene()
            document = self.state.document()
            next(el for el in document["elements"] if el["id"] == connector)[
                property_name
            ] = value
            self.state.replace(document)
            before = self.state.document()
            with self.assertRaisesRegex(SceneError, "not supported"):
                self.service.move(a, 10, 20)
            self.assertEqual(self.state.document(), before)

    def test_import_repairs_reverse_bindings_but_rejects_dangling_owner(self):
        container, label = rect(0, 0, 100, 100), text(25, 25, "A")
        label["containerId"] = container["id"]
        container["boundElements"] = [{"id": "stale", "type": "text"}]
        self.state.replace(new_document([container, label]))
        self.assertEqual(
            self.state.get(container["id"])["boundElements"],
            [{"id": label["id"], "type": "text"}],
        )
        before = self.state.document()
        label["containerId"] = "missing"
        with self.assertRaises(SceneError):
            self.state.replace(new_document([container, label]))
        self.assertEqual(self.state.document(), before)

    def test_labeled_creation_failure_does_not_add_shape(self):
        with patch.object(
            service_module, "text", side_effect=RuntimeError("label failed")
        ):
            with self.assertRaises(RuntimeError):
                self.service.add_shape("rectangle", 0, 0, 100, 100, "A")
        self.assertEqual(self.state.all(), [])

    def test_architecture_connectors_follow_generated_shapes(self):
        self.service.draw_architecture("box: API, box: Database")
        shape = next(el for el in self.state.all() if el["type"] == "rectangle")
        connector = next(el for el in self.state.all() if el["type"] == "arrow")
        self.assertEqual(connector["startBinding"]["elementId"], shape["id"])
        self.service.move(shape["id"], shape["x"] + 10, shape["y"])
        self.assertEqual(self.state.get(connector["id"])["x"], connector["x"] + 10)

    def test_load_and_generation_conflicts_preserve_intervening_edits(self):
        def load(_):
            self.service.add_shape("rectangle", 1, 1, 20, 20)
            return new_document()

        with patch.object(service_module, "load_scene", side_effect=load):
            with self.assertRaisesRegex(SceneError, "changed"):
                self.service.load("example")
        self.assertEqual(len(self.state.all()), 1)
        parser = service_module.parse_architecture

        def parse(prompt):
            self.service.add_shape("rectangle", 2, 2, 20, 20)
            return parser(prompt)

        with patch.object(service_module, "parse_architecture", side_effect=parse):
            with self.assertRaisesRegex(SceneError, "changed"):
                self.service.draw_architecture("box: API")
        self.assertEqual(len(self.state.all()), 2)


if __name__ == "__main__":
    unittest.main()
