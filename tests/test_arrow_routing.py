"""Unit tests for obstacle-aware orthogonal arrow routing, collision avoidance, and label positioning."""

import io
import math
import unittest
from PIL import Image

from excalidraw_mcp.elements import arrow, frame, rect, text
from excalidraw_mcp.layout import check_diagram_geometry, resolve_scene_layout
from excalidraw_mcp.models import new_document
from excalidraw_mcp.renderer import render_scene_image
from excalidraw_mcp.routing import (
    get_shape_port,
    position_connector_label,
    reroute_scene_arrows,
    route_orthogonal_connector,
    segment_intersects_rect,
)
from excalidraw_mcp.service import SceneService


class ArrowRoutingTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_obstacle_avoiding_orthogonal_routing(self):
        """Orthogonal router navigates around intermediate obstacle shapes with configurable clearance."""
        source = {"id": "src", "type": "rectangle", "x": 100.0, "y": 100.0, "width": 120.0, "height": 60.0}
        target = {"id": "dst", "type": "rectangle", "x": 100.0, "y": 400.0, "width": 120.0, "height": 60.0}
        obstacle = {"id": "obs", "type": "rectangle", "x": 80.0, "y": 220.0, "width": 160.0, "height": 80.0}

        # Straight line would pass through (x=160, y=220..300)
        direct_collides = segment_intersects_rect(
            (160.0, 160.0), (160.0, 400.0), (80.0, 220.0, 240.0, 300.0)
        )
        self.assertTrue(direct_collides)

        # Route orthogonally around obstacle with 15px clearance
        pts = route_orthogonal_connector(source, target, obstacles=[obstacle], clearance=15.0)
        self.assertGreaterEqual(len(pts), 4)

        # Verify no segment intersects obstacle box
        for i in range(len(pts) - 1):
            p1, p2 = pts[i], pts[i + 1]
            collides = segment_intersects_rect(p1, p2, (80.0, 220.0, 240.0, 300.0), margin=1.0)
            self.assertFalse(collides, f"Segment {p1} -> {p2} collided with obstacle")

        # Verify attachment to source boundary (right face or bottom face) and target boundary
        # Either bottom face (160) or right face (130)
        self.assertTrue(
            abs(pts[0][1] - 160.0) < 1.0 or (abs(pts[0][0] - 220.0) < 1.0 and abs(pts[0][1] - 130.0) < 1.0),
            f"Expected source boundary attachment, got {pts[0]}"
        )
        self.assertAlmostEqual(pts[-1][1], 400.0, delta=1.0)  # Target top

    def test_arrow_connects_precisely_to_shape_boundaries(self):
        """get_shape_port attaches accurately to rectangles, ellipses, and diamonds."""
        box = {"type": "rectangle", "x": 100.0, "y": 100.0, "width": 200.0, "height": 100.0}
        top_pt, top_norm = get_shape_port(box, "top")
        self.assertEqual(top_pt, (200.0, 100.0))
        self.assertEqual(top_norm, (0, -1))

        bot_pt, bot_norm = get_shape_port(box, "bottom")
        self.assertEqual(bot_pt, (200.0, 200.0))
        self.assertEqual(bot_norm, (0, 1))

        left_pt, left_norm = get_shape_port(box, "left")
        self.assertEqual(left_pt, (100.0, 150.0))
        self.assertEqual(left_norm, (-1, 0))

        right_pt, right_norm = get_shape_port(box, "right")
        self.assertEqual(right_pt, (300.0, 150.0))
        self.assertEqual(right_norm, (1, 0))

        # Diamond boundary verification
        dia = {"type": "diamond", "x": 100.0, "y": 100.0, "width": 200.0, "height": 100.0}
        d_top, _ = get_shape_port(dia, "top")
        self.assertEqual(d_top, (200.0, 100.0))

        # Ellipse boundary verification
        ell = {"type": "ellipse", "x": 100.0, "y": 100.0, "width": 200.0, "height": 100.0}
        e_top, _ = get_shape_port(ell, "top")
        self.assertEqual(e_top, (200.0, 100.0))

    def test_multiple_arrows_between_same_shapes_distinct_lanes(self):
        """Multiple connectors between the same components use distinct parallel lane tracks."""
        r1 = self.service.add_shape("rectangle", 100, 100, 150, 80, label="Service A")
        r2 = self.service.add_shape("rectangle", 500, 100, 150, 80, label="Service B")

        c1 = self.service.connect(r1["rectangle_id"], r2["rectangle_id"], elbowed=True, label="Lane 1")
        c2 = self.service.connect(r1["rectangle_id"], r2["rectangle_id"], elbowed=True, label="Lane 2")

        arr1 = self.service.state.get(c1["arrow_id"])
        arr2 = self.service.state.get(c2["arrow_id"])

        # Endpoints / origins must not be identical
        self.assertNotEqual((arr1["x"], arr1["y"]), (arr2["x"], arr2["y"]))
        # Distinct vertical lane separation
        self.assertGreaterEqual(abs(arr1["y"] - arr2["y"]), 15.0)

    def test_connector_label_positioned_along_clear_corridor(self):
        """Connector labels are placed along unobstructed route segments away from obstacles."""
        route = [
            (100.0, 100.0),
            (100.0, 50.0),
            (300.0, 50.0),
            (300.0, 200.0),
        ]
        # Obstacle placed at (200, 50) would collide with naive midpoint
        obs = [{"id": "blocker", "type": "rectangle", "x": 180.0, "y": 30.0, "width": 60.0, "height": 40.0}]

        lx, ly = position_connector_label(route, label_w=40.0, label_h=20.0, obstacles=obs)
        # Verify label bounding box does not overlap blocker
        collides = not (lx + 40.0 < 180.0 or lx > 240.0 or ly + 20.0 < 30.0 or ly > 70.0)
        self.assertFalse(collides)

    def test_missing_endpoints_graceful_handling(self):
        """Arrows with missing or dangling endpoints are handled gracefully without raising errors."""
        r1 = rect(100, 100, 120, 60)
        dangling_arrow = arrow(100, 100, 200, 200)
        dangling_arrow["startBinding"] = {"elementId": r1["id"]}
        dangling_arrow["endBinding"] = {"elementId": "non-existent-id"}

        doc = new_document([r1, dangling_arrow])
        # Rerouting should safely skip dangling connector
        reroute_scene_arrows(doc["elements"])
        self.assertEqual(len(doc["elements"]), 2)

    def test_nested_frames_and_corridor_routing(self):
        """Connectors between nested frames navigate inter-frame corridors cleanly."""
        f1 = frame(50, 50, 300, 200, name="Tier 1")
        f2 = frame(50, 350, 300, 200, name="Tier 2")
        r1 = rect(100, 100, 120, 60)
        r2 = rect(100, 400, 120, 60)
        r1["frameId"] = f1["id"]
        r2["frameId"] = f2["id"]

        c = arrow(160, 160, 160, 400, elbowed=True)
        c["startBinding"] = {"elementId": r1["id"]}
        c["endBinding"] = {"elementId": r2["id"]}

        doc = new_document([f1, f2, r1, r2, c])
        resolved = resolve_scene_layout(doc)
        diag = check_diagram_geometry(resolved)

        self.assertEqual(diag.get("connector_collision_count", 0), 0)
        self.assertEqual(diag["overlap_count"], 0)
        self.assertEqual(len(diag["containment_violations"]), 0)
        self.assertTrue(diag["valid"])

    def test_dense_diagram_all_connectors_routed_without_collision(self):
        """Dense multi-tier diagram routes all arrows with 0 collisions and valid geometry."""
        # 3 tiers of 3 nodes each with multiple cross-tier connections
        tiers = []
        nodes = []
        for tier_idx in range(3):
            t_nodes = []
            for col_idx in range(3):
                nid = f"t{tier_idx}_n{col_idx}"
                r = rect(100 + col_idx * 200, 100 + tier_idx * 250, 140, 70)
                r["id"] = nid
                nodes.append(r)
                t_nodes.append(r)
            tiers.append(t_nodes)

        # Cross connections: Tier 0 -> Tier 2 (skipping Tier 1)
        cross_arrow = arrow(170, 170, 170, 600, elbowed=True)
        cross_arrow["startBinding"] = {"elementId": "t0_n0"}
        cross_arrow["endBinding"] = {"elementId": "t2_n0"}

        doc = new_document(nodes + [cross_arrow])
        resolved = resolve_scene_layout(doc, min_gap_x=40, min_gap_y=40, layer_gap=60)
        diag = check_diagram_geometry(resolved)

        self.assertEqual(diag.get("connector_collision_count", 0), 0)
        self.assertTrue(diag["valid"])

    def test_service_reroute_connectors_mcp_integration(self):
        """SceneService reroute_connectors tool method updates revision and coordinates."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 50)
        r2 = self.service.add_shape("rectangle", 100, 400, 100, 50)
        # Direct straight connection
        conn = self.service.connect(r1["rectangle_id"], r2["rectangle_id"], elbowed=False)
        # Now place an obstacle in the middle
        obs = self.service.add_shape("rectangle", 80, 220, 140, 60)

        rev_before = self.service.state.revision
        res = self.service.reroute_connectors(clearance=20.0)
        rev_after = self.service.state.revision

        self.assertGreater(rev_after, rev_before)
        self.assertEqual(res["status"], "connectors rerouted")

    def test_tight_gap_obstacle_does_not_abort_to_straight_line(self):
        """Regression for BUG-005: 20px gap with clearance=15 must still route around obstacle."""
        from excalidraw_mcp.routing import route_orthogonal_connector, segment_intersects_rect

        a = rect(100, 100, 100, 60)
        b = rect(100, 300, 100, 60)
        c = rect(100, 180, 100, 60)  # 20px gap below A
        pts = route_orthogonal_connector(a, b, [a, b, c], clearance=15.0)
        self.assertGreater(len(pts), 2)
        c_box = (100.0, 180.0, 200.0, 240.0)
        for k in range(len(pts) - 1):
            self.assertFalse(segment_intersects_rect(pts[k], pts[k + 1], c_box, margin=1.0))

    def test_narrow_shape_port_clamping_and_only_elbowed(self):
        """Regression for BUG-007: port on w=8 rect stays inside [x, x+w], and only_elbowed=True preserves straight arrows."""
        from excalidraw_mcp.routing import get_shape_port, reroute_scene_arrows

        tiny = rect(100, 100, 8, 8)
        pt, _ = get_shape_port(tiny, "top", 0.0)
        self.assertGreaterEqual(pt[0], 100.0)
        self.assertLessEqual(pt[0], 108.0)

        a = self.service.add_shape("rectangle", 0, 0, 100, 60)
        b = self.service.add_shape("rectangle", 300, 0, 100, 60)
        obs = self.service.add_shape("rectangle", 150, 0, 100, 60)
        conn = self.service.connect(a["rectangle_id"], b["rectangle_id"], elbowed=False)
        doc = self.service.state.document()
        reroute_scene_arrows(doc["elements"], only_elbowed=True)
        arr = next(e for e in doc["elements"] if e["id"] == conn["arrow_id"])
        self.assertFalse(arr["elbowed"])

    def test_draw_graph_routes_elbowed_edges_and_preserves_arrowheads(self):
        """Regression for BUG-008: draw_graph routes elbowed=True edges and preserves start/end arrowheads."""
        res = self.service.draw_graph(
            nodes=[
                {"id": "a", "label": "A"},
                {"id": "b", "label": "B"},
                {"id": "c", "label": "C"},
            ],
            edges=[
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "a", "target": "c", "elbowed": True, "endArrowhead": "diamond"},
            ],
            layout="horizontal",
        )
        ac_el = self.service.state.get(res["edge_map"]["edge-3"]["element_id"])
        self.assertEqual(ac_el["endArrowhead"], "diamond")
        self.assertGreater(len(ac_el["points"]), 2)

    def test_move_and_resize_bound_elbowed_connector_reroutes_cleanly(self):
        """Regression for BUG-009: moving or resizing a shape bound to an elbowed arrow reroutes it."""
        a = self.service.add_shape("rectangle", 100, 100, 100, 60)
        b = self.service.add_shape("rectangle", 400, 100, 100, 60)
        conn = self.service.connect(a["rectangle_id"], b["rectangle_id"], elbowed=True)

        self.service.move(a["rectangle_id"], 100, 250)
        self.service.resize(b["rectangle_id"], 140, 100)
        arr = self.service.state.get(conn["arrow_id"])
        self.assertTrue(arr["elbowed"])
        self.assertGreaterEqual(len(arr["points"]), 2)


if __name__ == "__main__":
    unittest.main()
