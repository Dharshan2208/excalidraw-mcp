import io
import unittest
from PIL import Image

from excalidraw_mcp.elements import arrow, frame, rect, text
from excalidraw_mcp.layout import (
    architectural_layout,
    check_diagram_geometry,
    resolve_scene_layout,
)
from excalidraw_mcp.models import new_document
from excalidraw_mcp.renderer import render_scene_image
from excalidraw_mcp.service import SceneService


class ArchitectureScalingTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_check_diagram_geometry_detects_overlaps_and_containment(self):
        """check_diagram_geometry accurately reports overlaps and frame containment escapes."""
        # Create 2 overlapping rectangles
        r1 = rect(100, 100, 150, 100)
        r2 = rect(200, 100, 150, 100)  # Overlaps r1 horizontally by 50px
        # Create a frame that is too small for its child (placed away from r1, r2)
        f1 = frame(50, 390, 120, 80, name="Layer 1")
        r3 = rect(60, 400, 200, 100)  # Pokes 140px out of f1
        r3["frameId"] = f1["id"]

        doc = new_document([f1, r1, r2, r3])
        diag = check_diagram_geometry(doc)

        self.assertFalse(diag["valid"])
        self.assertEqual(diag["overlap_count"], 1)
        self.assertEqual(diag["overlaps"][0]["shape1_id"], r1["id"])
        self.assertEqual(diag["overlaps"][0]["shape2_id"], r2["id"])
        self.assertAlmostEqual(diag["overlaps"][0]["overlap_width"], 50.0, delta=1.0)

        # Containment violation detected
        self.assertEqual(len(diag["containment_violations"]), 1)
        self.assertEqual(diag["containment_violations"][0]["frame_id"], f1["id"])
        self.assertGreater(diag["containment_violations"][0]["overflow_x"], 0)

    def test_resolve_scene_layout_eliminates_all_overlaps(self):
        """resolve_scene_layout shifts colliding shapes and expands frames to achieve 0 overlaps."""
        # 3 colliding shapes in a tier
        r1 = rect(100, 100, 180, 100)
        r2 = rect(200, 100, 180, 100)  # Overlaps r1
        r3 = rect(300, 100, 180, 100)  # Overlaps r2
        f1 = frame(80, 60, 300, 140, name="Tier 1")
        for r in (r1, r2, r3):
            r["frameId"] = f1["id"]

        # Tier 2 placed right underneath, colliding vertically
        r4 = rect(100, 160, 200, 120)  # Collides with Tier 1
        f2 = frame(80, 150, 300, 140, name="Tier 2")
        r4["frameId"] = f2["id"]

        doc = new_document([f1, f2, r1, r2, r3, r4])
        before = check_diagram_geometry(doc)
        self.assertFalse(before["valid"])
        self.assertGreaterEqual(before["overlap_count"], 2)

        # Resolve layout
        resolved = resolve_scene_layout(doc, min_gap_x=40, min_gap_y=40, layer_gap=60)
        after = check_diagram_geometry(resolved)

        self.assertTrue(after["valid"], f"Expected 0 overlaps, got {after['overlaps']}")
        self.assertEqual(after["overlap_count"], 0)
        self.assertEqual(len(after["containment_violations"]), 0)

        # Verify horizontal gaps between r1, r2, r3 >= 40px
        idx = {e["id"]: e for e in resolved["elements"]}
        self.assertGreaterEqual(idx[r2["id"]]["x"] - (idx[r1["id"]]["x"] + idx[r1["id"]]["width"]), 39.0)
        self.assertGreaterEqual(idx[r3["id"]]["x"] - (idx[r2["id"]]["x"] + idx[r2["id"]]["width"]), 39.0)

        # Verify Tier 2 frame is positioned cleanly below Tier 1 frame
        t1_bottom = idx[f1["id"]]["y"] + idx[f1["id"]]["height"]
        t2_top = idx[f2["id"]]["y"]
        self.assertGreaterEqual(t2_top - t1_bottom, 59.0)

    def test_architectural_layout_two_pass_generation(self):
        """architectural_layout generates balanced tiers, wrapped rows, and collision-free frames."""
        tiers = [
            {
                "id": "tier-client",
                "name": "1. Client & Inbound Layer",
                "nodes": [
                    {"id": "web", "label": "Web Client Portal\n(Next.js App)", "shape": "rectangle"},
                    {"id": "mobile", "label": "Mobile App\n(Flutter)", "shape": "rectangle"},
                    {"id": "partner", "label": "Partner Integrations\n(REST API)", "shape": "rectangle"},
                ],
            },
            {
                "id": "tier-gw",
                "name": "2. API Gateway & Security",
                "nodes": [
                    {"id": "gw", "label": "Kong API Gateway\nRate Limiting & PASETO", "shape": "rectangle"},
                    {"id": "waf", "label": "WAF & DDoS Shield\n(Cloudflare)", "shape": "diamond"},
                ],
            },
            {
                "id": "tier-services",
                "name": "3. Microservices Core",
                "nodes": [
                    {"id": "svc_auth", "label": "Auth Service\n(Go / Gin)", "shape": "rectangle"},
                    {"id": "svc_events", "label": "Event Registry\n(Go / Gin)", "shape": "rectangle"},
                    {"id": "svc_payments", "label": "Payment Engine\n(Go / Gin)", "shape": "rectangle"},
                    {"id": "svc_notif", "label": "Notification Dispatcher\n(Go / Gin)", "shape": "rectangle"},
                ],
            },
        ]
        edges = [
            {"source": "web", "target": "gw", "label": "HTTPS"},
            {"source": "gw", "target": "svc_auth", "label": "Validate"},
            {"source": "gw", "target": "svc_events", "label": "Route"},
        ]

        result = architectural_layout(
            tiers,
            edges=edges,
            start_x=100,
            start_y=100,
            tier_gap=60,
            node_gap=40,
            max_tier_width=1800,
        )

        nodes = result["nodes"]
        frames = result["frames"]

        # 3 frames created for 3 tiers
        self.assertEqual(len(frames), 3)

        # Check that frames don't overlap vertically
        for i in range(len(frames) - 1):
            f1, f2 = frames[i], frames[i + 1]
            f1_bot = f1["y"] + f1["h"]
            self.assertGreaterEqual(f2["y"] - f1_bot, 55.0)

        # Check all nodes fit within their frames
        node_idx = {n["id"]: n for n in nodes}
        for f in frames:
            fid = f["id"]
            children = [n for n in nodes if n["frame_id"] == fid]
            for c in children:
                self.assertGreaterEqual(c["x"], f["x"])
                self.assertGreaterEqual(c["y"], f["y"])
                self.assertLessEqual(c["x"] + c["w"], f["x"] + f["w"] + 1.0)
                self.assertLessEqual(c["y"] + c["h"], f["y"] + f["h"] + 1.0)

    def test_dynamic_canvas_scaling_allows_8k_export_without_downscaling(self):
        """Exporting large diagrams with scale=2.0 generates high-res PNG up to 8192px."""
        service = SceneService()
        # Create a diagram spanning 2500x2000
        service.add_shape("rectangle", 50, 50, 300, 150, label="Origin Node")
        service.add_shape("rectangle", 2400, 1800, 300, 150, label="Far Corner Node")

        doc, _ = service.state.snapshot()
        # Standard scale=1.0 fits in 4096
        png_1x, w_1x, h_1x = render_scene_image(doc, scale=1.0)
        self.assertLessEqual(w_1x, 4096)
        self.assertLessEqual(h_1x, 4096)

        # High-res scale=2.0 scales above 4096 up to 8192 without premature downscaling
        png_2x, w_2x, h_2x = render_scene_image(doc, scale=2.0)
        self.assertGreater(w_2x, 4096)
        self.assertLessEqual(w_2x, 8192)

        im = Image.open(io.BytesIO(png_2x))
        self.assertEqual(im.size, (w_2x, h_2x))

    def test_service_resolve_layout_and_check_geometry(self):
        """SceneService resolve_layout() and check_geometry() integrate seamlessly."""
        # Add colliding shapes via service
        self.service.add_shape("rectangle", 100, 100, 200, 100, label="Box A")
        self.service.add_shape("rectangle", 220, 100, 200, 100, label="Box B")

        # Check geometry before resolution
        diag_before = self.service.check_geometry()
        self.assertFalse(diag_before["valid"])
        self.assertEqual(diag_before["overlap_count"], 1)

        # Resolve layout
        res = self.service.resolve_layout(min_gap_x=40)
        self.assertEqual(res["status"], "layout resolved")

        # Check geometry after resolution
        diag_after = self.service.check_geometry()
        self.assertTrue(diag_after["valid"])
        self.assertEqual(diag_after["overlap_count"], 0)

    def test_batch_mutate_with_auto_layout(self):
        """batch_mutate with auto_layout=True automatically eliminates collisions."""
        ops = [
            {"action": "add_rectangle", "client_id": "r1", "x": 100, "y": 100, "w": 200, "h": 100, "label": "Service 1"},
            {"action": "add_rectangle", "client_id": "r2", "x": 200, "y": 100, "w": 200, "h": 100, "label": "Service 2"},
        ]
        self.service.batch_mutate(ops, auto_layout=True)
        diag = self.service.check_geometry()
        self.assertTrue(diag["valid"])
        self.assertEqual(diag["overlap_count"], 0)

    def test_multi_session_service_isolation(self):
        """Verify SceneService isolates canvas drafts across multiple sessions without cross-contamination (M-008)."""
        self.assertEqual(self.service.session_id, "default")
        self.service.add_shape("rectangle", 10, 10, 100, 100, label="Default Canvas")

        # Spawn isolated sessions
        cursor_srv = self.service.for_session("cursor-session")
        claude_srv = self.service.for_session("claude-session")

        self.assertEqual(cursor_srv.session_id, "cursor-session")
        self.assertEqual(claude_srv.session_id, "claude-session")
        self.assertIn("default", self.service.list_sessions())
        self.assertIn("cursor-session", self.service.list_sessions())
        self.assertIn("claude-session", self.service.list_sessions())

        # Fresh sessions start empty
        self.assertEqual(cursor_srv.get_scene_summary()["element_count"], 0)
        self.assertEqual(claude_srv.get_scene_summary()["element_count"], 0)

        # Mutate cursor session
        cursor_srv.add_shape("rectangle", 50, 50, 120, 80, label="Cursor Box")
        cursor_srv.add_text(50, 200, "Cursor Architecture Note")
        self.assertEqual(cursor_srv.get_scene_summary()["element_count"], 3)  # rect + label + standalone text

        # Verify claude session remains unpolluted
        self.assertEqual(claude_srv.get_scene_summary()["element_count"], 0)

        # Mutate claude session
        claude_srv.add_shape("diamond", 200, 200, 80, 80, label="Claude Decision")
        self.assertEqual(claude_srv.get_scene_summary()["element_count"], 2)  # diamond + label

        # Verify cursor session was not modified by claude
        self.assertEqual(cursor_srv.get_scene_summary()["element_count"], 3)

        # Clear cursor session, verify claude session remains intact
        cursor_srv.clear()
        self.assertEqual(cursor_srv.get_scene_summary()["element_count"], 0)
        self.assertEqual(claude_srv.get_scene_summary()["element_count"], 2)

        # Switch main service to claude session
        self.service.switch_session("claude-session")
        self.assertEqual(self.service.session_id, "claude-session")
        self.assertEqual(self.service.get_scene_summary()["element_count"], 2)

    def test_multi_session_server_and_resource_isolation(self):
        """Verify FastMCP servers bound to different sessions maintain independent active resources (M-008)."""
        import asyncio
        import json
        from excalidraw_mcp.server import create_server

        server_a = create_server(session_id="workspace-alpha")
        server_b = create_server(session_id="workspace-beta")

        async def run_scenario():
            # Workspace Alpha adds a shape
            res_a = await server_a.call_tool(
                "create_shape",
                {"type": "rectangle", "x": 100, "y": 100, "w": 150, "h": 80, "label": "Alpha"},
            )
            # Workspace Beta adds a circle
            res_b = await server_b.call_tool(
                "create_shape",
                {"type": "circle", "x": 300, "y": 300, "w": 100, "label": "Beta"},
            )

            # Inspect capabilities and sessions
            res_cap_a = await server_a.read_resource("excalidraw://capabilities")
            res_cap_b = await server_b.read_resource("excalidraw://capabilities")
            cap_a = json.loads(res_cap_a.contents[0].content)
            cap_b = json.loads(res_cap_b.contents[0].content)
            self.assertEqual(cap_a["session_id"], "workspace-alpha")
            self.assertEqual(cap_b["session_id"], "workspace-beta")

            # Read active scene resources
            res_doc_a = await server_a.read_resource("excalidraw://active/scene.json")
            res_doc_b = await server_b.read_resource("excalidraw://active/scene.json")
            doc_a = json.loads(res_doc_a.contents[0].content)
            doc_b = json.loads(res_doc_b.contents[0].content)

            # Alpha has rectangle + label
            alpha_types = [e["type"] for e in doc_a["elements"]]
            self.assertIn("rectangle", alpha_types)
            self.assertNotIn("ellipse", alpha_types)

            # Beta has ellipse + label
            beta_types = [e["type"] for e in doc_b["elements"]]
            self.assertIn("ellipse", beta_types)
            self.assertNotIn("rectangle", beta_types)

        asyncio.run(run_scenario())


if __name__ == "__main__":
    unittest.main()
