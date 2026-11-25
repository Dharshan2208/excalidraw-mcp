"""Phase-by-phase regression and integration tests for scene-aware connector routing."""

import json
import unittest

from fastmcp import Client

from excalidraw_mcp.auto_fix import auto_fix_scene_layout
from excalidraw_mcp.elements import arrow, frame, rect, text
from excalidraw_mcp.models import new_document
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class Phase1PolicyAndContextTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_routing_mode_straight_is_preserved_across_reroute_and_auto_fix(self):
        """Phase 1: Explicit routing_mode='straight' must never be forced to elbowed=True."""
        from excalidraw_mcp.routing import reroute_scene_arrows, resolve_arrow_routing_mode

        a = self.service.add_shape("rectangle", 100, 100, 100, 60, label="A")
        obs = self.service.add_shape("rectangle", 240, 80, 100, 100, label="Obs")
        b = self.service.add_shape("rectangle", 400, 100, 100, 60, label="B")

        conn = self.service.connect(
            a["rectangle_id"], b["rectangle_id"], label="direct", routing_mode="straight"
        )
        arr = self.service.state.get(conn["arrow_id"])
        self.assertEqual(resolve_arrow_routing_mode(arr), "straight")
        self.assertFalse(arr["elbowed"])
        self.assertEqual(len(arr["points"]), 2)

        doc = self.service.state.document()
        reroute_scene_arrows(doc["elements"], only_elbowed=False)
        arr_after = next(e for e in doc["elements"] if e["id"] == conn["arrow_id"])
        self.assertFalse(arr_after["elbowed"])
        self.assertEqual(len(arr_after["points"]), 2)

        fixed = auto_fix_scene_layout(self.service.state.document(), repair_scope="connectors")
        arr_fixed = next(e for e in fixed["document"]["elements"] if e["id"] == conn["arrow_id"])
        self.assertFalse(arr_fixed["elbowed"])
        self.assertEqual(len(arr_fixed["points"]), 2)

    def test_build_scene_routing_context_classifies_structures_and_collects_metadata(self):
        """Phase 1: SceneRoutingContext collects obstacles, frame headers, segments, labels, and structure."""
        from excalidraw_mcp.routing import build_scene_routing_context

        f1 = frame(50, 50, 300, 200, name="Auth")
        r1 = rect(80, 100, 100, 60)
        r1["frameId"] = f1["id"]
        r2 = rect(220, 100, 100, 60)
        r2["frameId"] = f1["id"]
        arr = arrow(180, 130, 220, 130)
        arr["startBinding"] = {"elementId": r1["id"]}
        arr["endBinding"] = {"elementId": r2["id"]}
        lbl = text(190, 110, "token", fontSize=14)
        lbl["containerId"] = arr["id"]

        ctx = build_scene_routing_context([f1, r1, r2, arr, lbl])
        self.assertEqual(ctx.structure, "clustered")
        self.assertEqual(len(ctx.frame_headers), 1)
        self.assertEqual(ctx.frame_headers[0], (50.0, 50.0, 350.0, 78.0))
        self.assertGreater(len(ctx.existing_segments), 0)
        self.assertGreater(len(ctx.label_boxes), 0)
        self.assertGreater(ctx.density, 0.0)


class Phase1MCPContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_diagram_routing_mode_and_per_edge_override(self):
        """Phase 1: generate_diagram accepts routing_mode with per-edge GraphEdge override."""
        service = SceneService()
        server = create_server(service, toolset="full")

        async with Client(server) as client:
            res = await client.call_tool(
                "generate_diagram",
                {
                    "format": "graph",
                    "routing_mode": "orthogonal",
                    "nodes": [
                        {"id": "a", "label": "A"},
                        {"id": "b", "label": "B"},
                        {"id": "c", "label": "C"},
                    ],
                    "edges": [
                        {"id": "e1", "source": "a", "target": "b"},
                        {"id": "e2", "source": "b", "target": "c"},
                        {"id": "e3", "source": "a", "target": "c", "routing_mode": "straight"},
                    ],
                },
            )
            self.assertFalse(res.is_error)
            data = json.loads(res.content[0].text)
            e1 = service.state.get(data["edge_map"]["e1"]["element_id"])
            e3 = service.state.get(data["edge_map"]["e3"]["element_id"])
            self.assertTrue(e1["elbowed"])
            self.assertFalse(e3["elbowed"])
            self.assertEqual(len(e3["points"]), 2)
            self.assertEqual((e3.get("customData") or {}).get("routing_mode"), "straight")


class Phase2SceneRouterAndMultiCriteriaTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_auto_mode_picks_straight_diagonal_when_clear_and_orthogonal_when_blocked(self):
        """Phase 2: routing_mode='auto' picks straight diagonal when clear, orthogonal when blocked."""
        a = self.service.add_shape("rectangle", 100, 100, 100, 60, label="A")
        b = self.service.add_shape("rectangle", 340, 260, 100, 60, label="B")
        c1 = self.service.connect(a["rectangle_id"], b["rectangle_id"], routing_mode="auto")
        arr1 = self.service.state.get(c1["arrow_id"])
        self.assertFalse(arr1["elbowed"])
        self.assertEqual(len(arr1["points"]), 2)

        # Now add an obstacle directly on a second auto path
        self.service.clear()
        s = self.service.add_shape("rectangle", 100, 100, 100, 60, label="S")
        obs = self.service.add_shape("rectangle", 240, 80, 100, 100, label="Obs")
        t = self.service.add_shape("rectangle", 400, 100, 100, 60, label="T")
        c2 = self.service.connect(s["rectangle_id"], t["rectangle_id"], routing_mode="auto")
        arr2 = self.service.state.get(c2["arrow_id"])
        self.assertTrue(arr2["elbowed"])
        self.assertGreater(len(arr2["points"]), 2)

    def test_orthogonal_router_avoids_crossing_existing_arrow_and_frame_headers(self):
        """Phase 2: Multi-criteria A* avoids crossing an existing arrow and frame header band."""
        from excalidraw_mcp.routing import (
            build_scene_routing_context,
            route_connector_scene_aware,
            segment_intersects_rect,
        )

        f1 = frame(80, 80, 320, 220, name="Cluster")
        a = rect(110, 140, 100, 60)
        a["frameId"] = f1["id"]
        b = rect(260, 140, 100, 60)
        b["frameId"] = f1["id"]
        c = rect(480, 140, 100, 60)

        # Route A -> C with B blocking the middle and F1 header at y=80..108
        ctx = build_scene_routing_context([f1, a, b, c])
        pts, chosen = route_connector_scene_aware(a, c, ctx, routing_mode="orthogonal")
        self.assertEqual(chosen, "orthogonal")
        header_rect = (80.0, 80.0, 400.0, 108.0)
        b_rect = (260.0, 140.0, 360.0, 200.0)
        for i in range(len(pts) - 1):
            self.assertFalse(segment_intersects_rect(pts[i], pts[i + 1], b_rect, margin=1.0))
            self.assertFalse(segment_intersects_rect(pts[i], pts[i + 1], header_rect, margin=1.0))

    def test_moving_unrelated_node_onto_auto_straight_path_triggers_reroute(self):
        """Phase 2: Moving a third node into an existing auto straight connector reroutes it."""
        a = self.service.add_shape("rectangle", 100, 100, 100, 60, label="A")
        b = self.service.add_shape("rectangle", 420, 100, 100, 60, label="B")
        obs = self.service.add_shape("rectangle", 260, 260, 100, 60, label="Obs")

        conn = self.service.connect(a["rectangle_id"], b["rectangle_id"], routing_mode="auto")
        self.assertFalse(self.service.state.get(conn["arrow_id"])["elbowed"])

        # Move obs right across A -> B path
        self.service.move(obs["rectangle_id"], 260, 100)
        arr_after = self.service.state.get(conn["arrow_id"])
        self.assertTrue(arr_after["elbowed"])
        self.assertGreater(len(arr_after["points"]), 2)

    def test_fan_in_connectors_distribute_ports_on_shared_face(self):
        """Phase 2: Multiple connectors targeting the same shape face distribute ports cleanly."""
        a1 = self.service.add_shape("rectangle", 100, 60, 100, 50, label="A1")
        a2 = self.service.add_shape("rectangle", 100, 140, 100, 50, label="A2")
        a3 = self.service.add_shape("rectangle", 100, 220, 100, 50, label="A3")
        tgt = self.service.add_shape("rectangle", 360, 110, 120, 120, label="Target")

        c1 = self.service.connect(a1["rectangle_id"], tgt["rectangle_id"], routing_mode="orthogonal")
        c2 = self.service.connect(a2["rectangle_id"], tgt["rectangle_id"], routing_mode="orthogonal")
        c3 = self.service.connect(a3["rectangle_id"], tgt["rectangle_id"], routing_mode="orthogonal")

        doc = self.service.state.document()
        from excalidraw_mcp.routing import reroute_scene_arrows
        reroute_scene_arrows(doc["elements"])
        ends = []
        for cid in (c1["arrow_id"], c2["arrow_id"], c3["arrow_id"]):
            el = next(e for e in doc["elements"] if e["id"] == cid)
            last_pt = el["points"][-1]
            ends.append((round(el["x"] + last_pt[0], 1), round(el["y"] + last_pt[1], 1)))
        self.assertEqual(len(set(ends)), 3)


if __name__ == "__main__":
    unittest.main()
