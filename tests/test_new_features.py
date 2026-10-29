"""Comprehensive tests for new MCP features:
- Adaptive Roundness & Elbowed Connectors
- Frames & Subgraphs (add_frame & Clustered Layouts)
- Element Query (find_elements)
- Batch Mutation (batch_mutate) with Atomicity & Dynamic ID Resolution
"""

import asyncio
import unittest

from fastmcp import Client
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class AdaptiveRoundnessAndElbowedTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_add_rectangle_with_roundness_modes(self):
        # Adaptive (Excalidraw type 3)
        res_adaptive = self.service.add_shape(
            "rectangle", 0, 0, 100, 100, roundness="adaptive"
        )
        el_adaptive = self.state.get(res_adaptive["rectangle_id"])
        self.assertEqual(el_adaptive["roundness"], {"type": 3})

        # Round (Excalidraw type 2)
        res_round = self.service.add_shape(
            "rectangle", 120, 0, 100, 100, roundness="round"
        )
        el_round = self.state.get(res_round["rectangle_id"])
        self.assertEqual(el_round["roundness"], {"type": 2})

        # Sharp (None)
        res_sharp = self.service.add_shape(
            "rectangle", 240, 0, 100, 100, roundness="sharp"
        )
        el_sharp = self.state.get(res_sharp["rectangle_id"])
        self.assertIsNone(el_sharp["roundness"])

        # Default omitted is None for backward compatibility
        res_default = self.service.add_shape("rectangle", 360, 0, 100, 100)
        el_default = self.state.get(res_default["rectangle_id"])
        self.assertIsNone(el_default["roundness"])

    def test_add_diamond_with_roundness(self):
        res = self.service.add_shape("diamond", 0, 0, 100, 100, roundness="adaptive")
        el = self.state.get(res["diamond_id"])
        self.assertEqual(el["roundness"], {"type": 3})

    def test_update_element_changes_roundness(self):
        res = self.service.add_shape("rectangle", 0, 0, 100, 100)
        rect_id = res["rectangle_id"]
        self.assertIsNone(self.state.get(rect_id)["roundness"])

        self.service.update_element(rect_id, roundness="adaptive")
        self.assertEqual(self.state.get(rect_id)["roundness"], {"type": 3})

        self.service.update_element(rect_id, roundness="round")
        self.assertEqual(self.state.get(rect_id)["roundness"], {"type": 2})

        self.service.update_element(rect_id, roundness="sharp")
        self.assertIsNone(self.state.get(rect_id)["roundness"])

    def test_arrow_and_connector_elbowed_support(self):
        res_arrow = self.service.add_arrow(0, 0, 100, 100, elbowed=True)
        arrow_el = self.state.get(res_arrow["arrow_id"])
        self.assertTrue(arrow_el["elbowed"])

        # Connect two shapes with elbowed=True
        a = self.service.add_shape("rectangle", 0, 0, 100, 80)["rectangle_id"]
        b = self.service.add_shape("rectangle", 300, 200, 100, 80)["rectangle_id"]
        conn_res = self.service.connect(a, b, label="Bus", elbowed=True)
        conn_el = self.state.get(conn_res["arrow_id"])
        self.assertTrue(conn_el["elbowed"])

        # Update connector elbowed property
        self.service.update_element(conn_res["arrow_id"], elbowed=False)
        self.assertFalse(self.state.get(conn_res["arrow_id"])["elbowed"])


class FramesAndSubgraphsTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_add_frame_empty_and_with_elements(self):
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60, label="App")
        r2 = self.service.add_shape("rectangle", 220, 100, 80, 60, label="DB")

        frame_res = self.service.add_frame(
            "VPC Network",
            80,
            60,
            260,
            140,
            element_ids=[r1["rectangle_id"], r2["rectangle_id"]],
        )
        frame_id = frame_res["frame_id"]
        frame_el = self.state.get(frame_id)

        self.assertEqual(frame_el["type"], "frame")
        self.assertEqual(frame_el["name"], "VPC Network")
        self.assertEqual(frame_el["x"], 80)
        self.assertEqual(frame_el["y"], 60)
        self.assertEqual(frame_el["width"], 260)
        self.assertEqual(frame_el["height"], 140)

        # Children and their labels should have frameId set
        self.assertEqual(self.state.get(r1["rectangle_id"])["frameId"], frame_id)
        self.assertEqual(self.state.get(r1["label_id"])["frameId"], frame_id)
        self.assertEqual(self.state.get(r2["rectangle_id"])["frameId"], frame_id)
        self.assertEqual(self.state.get(r2["label_id"])["frameId"], frame_id)

    def test_moving_frame_translates_children_and_connectors(self):
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60)["rectangle_id"]
        r2 = self.service.add_shape("rectangle", 220, 100, 80, 60)["rectangle_id"]
        conn = self.service.connect(r1, r2, label="Internal")["arrow_id"]

        frame_id = self.service.add_frame(
            "Cluster", 80, 80, 260, 120, element_ids=[r1, r2]
        )["frame_id"]

        # Move frame by +50 x, +30 y (new position: 130, 110)
        self.service.move(frame_id, 130, 110)

        # Frame position
        self.assertEqual(self.state.get(frame_id)["x"], 130)
        self.assertEqual(self.state.get(frame_id)["y"], 110)

        # Child elements must have translated by (50, 30)
        self.assertEqual(self.state.get(r1)["x"], 150)
        self.assertEqual(self.state.get(r1)["y"], 130)
        self.assertEqual(self.state.get(r2)["x"], 270)
        self.assertEqual(self.state.get(r2)["y"], 130)

        # Internal connector endpoints should have followed
        conn_el = self.state.get(conn)
        self.assertEqual(conn_el["x"], 230)
        self.assertEqual(conn_el["y"], 160)

    def test_deleting_frame_unparents_contained_elements(self):
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60)["rectangle_id"]
        frame_id = self.service.add_frame(
            "Subnet", 50, 50, 200, 200, element_ids=[r1]
        )["frame_id"]

        self.assertEqual(self.state.get(r1)["frameId"], frame_id)

        # Delete the frame
        del_res = self.service.delete(frame_id)
        self.assertEqual(del_res["status"], "deleted")
        self.assertIsNone(self.state.get(frame_id))

        # Contained child survives with frameId cleared
        child = self.state.get(r1)
        self.assertIsNotNone(child)
        self.assertIsNone(child["frameId"])

    def test_reparenting_via_update_element(self):
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60)["rectangle_id"]
        f1 = self.service.add_frame("Frame 1", 50, 50, 200, 200)["frame_id"]
        f2 = self.service.add_frame("Frame 2", 300, 50, 200, 200)["frame_id"]

        self.assertIsNone(self.state.get(r1)["frameId"])

        # Assign to f1
        self.service.update_element(r1, frame_id=f1)
        self.assertEqual(self.state.get(r1)["frameId"], f1)

        # Move to f2
        self.service.update_element(r1, frame_id=f2)
        self.assertEqual(self.state.get(r1)["frameId"], f2)

        # Clear frame parent
        self.service.update_element(r1, frame_id="")
        self.assertIsNone(self.state.get(r1)["frameId"])

    def test_clustered_graph_layout(self):
        nodes = [
            {"id": "fe1", "label": "Web 1", "shape": "rectangle", "cluster": "frontend"},
            {"id": "fe2", "label": "Web 2", "shape": "rectangle", "cluster": "frontend"},
            {"id": "be1", "label": "API", "shape": "diamond", "cluster": "backend"},
            {"id": "db1", "label": "Primary DB", "shape": "ellipse", "cluster": "backend"},
            {"id": "ext", "label": "DNS", "shape": "rectangle"},  # unclustered
        ]
        edges = [
            {"source": "fe1", "target": "be1", "label": "HTTP"},
            {"source": "fe2", "target": "be1", "label": "HTTP"},
            {"source": "be1", "target": "db1", "label": "SQL"},
            {"source": "ext", "target": "fe1", "label": "Route"},
        ]
        clusters = [
            {"id": "frontend", "label": "Frontend Tier"},
            {"id": "backend", "label": "Backend Tier"},
        ]

        result = self.service.draw_graph(
            nodes,
            edges,
            clusters=clusters,
            layout="layered",
            direction="horizontal",
            elbowed=True,
            roundness="adaptive",
        )

        self.assertEqual(result["status"], "graph drawn")
        self.assertIn("cluster_map", result)
        self.assertEqual(len(result["cluster_map"]), 2)

        fe_frame_id = result["cluster_map"]["frontend"]
        be_frame_id = result["cluster_map"]["backend"]

        # Validate frames exist and have the proper labels
        fe_frame = self.state.get(fe_frame_id)
        be_frame = self.state.get(be_frame_id)
        self.assertEqual(fe_frame["name"], "Frontend Tier")
        self.assertEqual(be_frame["name"], "Backend Tier")

        # Frontend frame and backend frame do not overlap along the horizontal axis
        self.assertTrue(
            fe_frame["x"] + fe_frame["width"] < be_frame["x"]
            or be_frame["x"] + be_frame["width"] < fe_frame["x"]
        )

        # Verify child node bindings
        fe1_el = self.state.get(result["node_map"]["fe1"]["element_id"])
        be1_el = self.state.get(result["node_map"]["be1"]["element_id"])
        ext_el = self.state.get(result["node_map"]["ext"]["element_id"])

        self.assertEqual(fe1_el["frameId"], fe_frame_id)
        self.assertEqual(be1_el["frameId"], be_frame_id)
        self.assertIsNone(ext_el["frameId"])

        # Check roundness applied
        self.assertEqual(fe1_el["roundness"], {"type": 3})

        # Check elbowed connectors
        for edge_info in result["edge_map"].values():
            arrow_el = self.state.get(edge_info["element_id"])
            self.assertTrue(arrow_el["elbowed"])


class ElementQueryTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

        # Build test canvas
        self.r1 = self.service.add_shape("rectangle", 0, 0, 100, 80, label="Auth Service")
        self.r2 = self.service.add_shape("rectangle", 200, 0, 100, 80, label="Billing Service")
        self.d1 = self.service.add_shape("diamond", 400, 0, 100, 80, label="Payment Gateway")
        self.t1 = self.service.add_text(50, 150, "Architecture Note: Draft")
        self.conn = self.service.connect(
            self.r2["rectangle_id"], self.d1["diamond_id"], label="Stripe API"
        )
        self.frame = self.service.add_frame(
            "Secure Enclave", -20, -20, 250, 120, element_ids=[self.r1["rectangle_id"]]
        )

    def test_find_by_text_query(self):
        # Query matches label on rectangle
        res_auth = self.service.find_elements(query="auth")
        self.assertEqual(res_auth["total"], 1)
        self.assertEqual(res_auth["matches"][0]["id"], self.r1["rectangle_id"])
        self.assertEqual(res_auth["matches"][0]["label"], "Auth Service")

        # Query matches standalone text
        res_note = self.service.find_elements(query="draft")
        self.assertEqual(res_note["total"], 1)
        self.assertEqual(res_note["matches"][0]["id"], self.t1["text_id"])

        # Query matches frame name
        res_frame = self.service.find_elements(query="enclave")
        self.assertEqual(res_frame["total"], 1)
        self.assertEqual(res_frame["matches"][0]["name"], "Secure Enclave")

        # Query matches arrow label
        res_stripe = self.service.find_elements(query="stripe")
        self.assertEqual(res_stripe["total"], 1)
        self.assertEqual(res_stripe["matches"][0]["id"], self.conn["arrow_id"])

    def test_find_by_type_filter(self):
        res_rects = self.service.find_elements(type="rectangle")
        self.assertEqual(res_rects["total"], 2)

        res_diamonds = self.service.find_elements(type="diamond")
        self.assertEqual(res_diamonds["total"], 1)
        self.assertEqual(res_diamonds["matches"][0]["id"], self.d1["diamond_id"])

        res_frames = self.service.find_elements(type="frame")
        self.assertEqual(res_frames["total"], 1)
        self.assertEqual(res_frames["matches"][0]["id"], self.frame["frame_id"])

    def test_find_by_frame_id(self):
        res_frame_children = self.service.find_elements(
            frame_id=self.frame["frame_id"], include_bound_labels=True
        )
        # r1 and its label belong to the frame
        self.assertEqual(res_frame_children["total"], 2)
        child_ids = {m["id"] for m in res_frame_children["matches"]}
        self.assertIn(self.r1["rectangle_id"], child_ids)
        self.assertIn(self.r1["label_id"], child_ids)

        # By default (without include_bound_labels), only top-level frame children are returned
        res_top_level = self.service.find_elements(frame_id=self.frame["frame_id"])
        self.assertEqual(res_top_level["total"], 1)
        self.assertEqual(res_top_level["matches"][0]["id"], self.r1["rectangle_id"])

    def test_find_by_connected_to(self):
        res_connected = self.service.find_elements(connected_to=self.d1["diamond_id"])
        # Should return the connector and the billing service shape
        connected_ids = {m["id"] for m in res_connected["matches"]}
        self.assertIn(self.conn["arrow_id"], connected_ids)
        self.assertIn(self.r2["rectangle_id"], connected_ids)
        self.assertNotIn(self.r1["rectangle_id"], connected_ids)


class BatchMutateTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_atomic_batch_with_dynamic_client_id_resolution(self):
        operations = [
            {
                "action": "add_rectangle",
                "client_id": "box_a",
                "x": 0,
                "y": 0,
                "w": 120,
                "h": 80,
                "label": "Ingress",
                "roundness": "adaptive",
            },
            {
                "action": "add_diamond",
                "client_id": "box_b",
                "x": 200,
                "y": 0,
                "w": 100,
                "h": 80,
                "label": "Router",
            },
            {
                "action": "connect",
                "client_id": "edge_1",
                "source_id": "box_a",
                "target_id": "box_b",
                "label": "Forward",
                "elbowed": True,
            },
            {
                "action": "add_frame",
                "client_id": "vpc_frame",
                "name": "Edge Tier",
                "x": -20,
                "y": -30,
                "w": 360,
                "h": 140,
                "element_ids": ["box_a", "box_b"],
            },
            {
                "action": "move",
                "element_id": "vpc_frame",
                "x": 50,
                "y": 50,
            },
            {
                "action": "update_element",
                "element_id": "box_a",
                "strokeColor": "#0000ff",
            },
        ]

        initial_rev = self.state.revision
        result = self.service.batch_mutate(operations)

        self.assertEqual(result["status"], "batch executed")
        self.assertEqual(result["operations_executed"], 6)
        self.assertGreater(result["revision"], initial_rev)

        ref_map = result["ref_map"]
        self.assertIn("box_a", ref_map)
        self.assertIn("box_b", ref_map)
        self.assertIn("edge_1", ref_map)
        self.assertIn("vpc_frame", ref_map)

        box_a = self.state.get(ref_map["box_a"])
        self.assertEqual(box_a["strokeColor"], "#0000ff")
        self.assertEqual(box_a["roundness"], {"type": 3})
        self.assertEqual(box_a["frameId"], ref_map["vpc_frame"])

        # Frame was moved to 50, 50 (from -20, -30 -> delta +70, +80)
        # box_a was at 0, 0 -> should now be at 70, 80
        self.assertEqual(box_a["x"], 70)
        self.assertEqual(box_a["y"], 80)

        edge = self.state.get(ref_map["edge_1"])
        self.assertTrue(edge["elbowed"])

    def test_batch_atomic_rollback_on_failure(self):
        # Pre-populate state
        self.service.add_shape("rectangle", 0, 0, 100, 100, label="Existing")
        initial_doc = self.state.document()
        initial_rev = self.state.revision

        # Failing batch: 2 valid operations followed by an invalid one (missing target element)
        failing_ops = [
            {"action": "add_rectangle", "x": 100, "y": 100, "w": 50, "h": 50, "client_id": "temp1"},
            {"action": "add_rectangle", "x": 200, "y": 100, "w": 50, "h": 50, "client_id": "temp2"},
            {"action": "connect", "source_id": "temp1", "target_id": "nonexistent_target_id"},
        ]

        with self.assertRaisesRegex(SceneError, "not found"):
            self.service.batch_mutate(failing_ops)

        # Confirm 100% rollback: scene document and revision are identical
        self.assertEqual(self.state.document(), initial_doc)
        self.assertEqual(self.state.revision, initial_rev)

    def test_batch_rejection_on_invalid_parameters(self):
        # Empty batch
        with self.assertRaisesRegex(SceneError, "non-empty"):
            self.service.batch_mutate([])

        # Negative dimensions
        with self.assertRaisesRegex(SceneError, "positive"):
            self.service.batch_mutate([
                {"action": "add_rectangle", "x": 0, "y": 0, "w": -10, "h": 50}
            ])

        # Unknown action
        with self.assertRaisesRegex(SceneError, "Unknown action"):
            self.service.batch_mutate([
                {"action": "invalid_action_name"}
            ])


class MCPProtocolContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_protocol_invokes_new_tools_end_to_end(self):
        server = create_server(toolset="full")
        async with Client(server, timeout=5) as client:
            # 1. Test add_frame
            f_res = await client.call_tool(
                "add_frame",
                {"name": "Cluster", "x": 0, "y": 0, "w": 300, "h": 200},
            )
            self.assertFalse(f_res.is_error)
            frame_id = f_res.structured_content["frame_id"]

            # 2. Test add_rectangle with adaptive roundness inside frame
            r_res = await client.call_tool(
                "add_rectangle",
                {
                    "x": 20,
                    "y": 20,
                    "w": 100,
                    "h": 60,
                    "label": "Worker",
                    "roundness": "adaptive",
                    "frame_id": frame_id,
                },
            )
            self.assertFalse(r_res.is_error)
            rect_id = r_res.structured_content["rectangle_id"]

            # 3. Test find_elements
            find_res = await client.call_tool(
                "find_elements",
                {"query": "Worker"},
            )
            self.assertFalse(find_res.is_error)
            self.assertEqual(find_res.structured_content["total"], 1)
            self.assertEqual(
                find_res.structured_content["matches"][0]["id"], rect_id
            )

            # 4. Test batch_mutate
            batch_res = await client.call_tool(
                "batch_mutate",
                {
                    "operations": [
                        {
                            "action": "add_diamond",
                            "client_id": "d1",
                            "x": 150,
                            "y": 20,
                            "w": 80,
                            "h": 60,
                            "label": "Router",
                        },
                        {
                            "action": "connect",
                            "source_id": rect_id,
                            "target_id": "d1",
                            "elbowed": True,
                        },
                    ]
                },
            )
            self.assertFalse(batch_res.is_error)
            self.assertEqual(
                batch_res.structured_content["operations_executed"], 2
            )
            self.assertIn("d1", batch_res.structured_content["ref_map"])


            # 5. Test preview tool over MCP protocol
            preview_res = await client.call_tool(
                "preview",
                {"scale": 1.5, "padding": 30},
            )
            self.assertFalse(preview_res.is_error)
            self.assertIsNotNone(preview_res.content)
            self.assertEqual(len(preview_res.content), 1)
            img_content = preview_res.content[0]
            self.assertEqual(img_content.type, "image")
            self.assertEqual(img_content.mimeType, "image/png")
            import base64

            raw_bytes = base64.b64decode(img_content.data)
            self.assertEqual(raw_bytes[:8], b"\x89PNG\r\n\x1a\n")


class ImagePreviewTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.state = self.service.state

    def test_empty_canvas_preview(self):
        png = self.service.preview()
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")

    def test_complex_scene_preview(self):
        r = self.service.add_shape(
            "rectangle",
            100,
            100,
            120,
            80,
            label="Worker Node",
            roundness="adaptive",
            strokeColor="#0055aa",
            backgroundColor="#eef5ff",
        )
        d = self.service.add_shape(
            "diamond",
            300,
            100,
            100,
            80,
            label="Decision",
            strokeColor="#aa5500",
            backgroundColor="#fff5ee",
        )
        c = self.service.add_shape(
            "ellipse",
            100,
            260,
            80,
            80,
            label="Database",
            strokeColor="#00aa55",
            backgroundColor="#eeffee",
        )
        self.service.connect(
            r["rectangle_id"], d["diamond_id"], label="Process", elbowed=True
        )
        self.service.add_frame(
            "Cluster VPC", 60, 60, 400, 320, element_ids=[r["rectangle_id"]]
        )

        png_1x = self.service.preview(scale=1.0, padding=40)
        self.assertEqual(png_1x[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(png_1x), 1000)

        png_2x = self.service.preview(scale=2.0, padding=20)
        self.assertEqual(png_2x[:8], b"\x89PNG\r\n\x1a\n")
        # Higher scale should yield more image data
        self.assertGreater(len(png_2x), len(png_1x))

    def test_preview_rejects_invalid_inputs(self):
        with self.assertRaisesRegex(SceneError, "scale"):
            self.service.preview(scale=0.1)

        with self.assertRaisesRegex(SceneError, "scale"):
            self.service.preview(scale=10.0)

        with self.assertRaisesRegex(SceneError, "padding"):
            self.service.preview(padding=-5)

        with self.assertRaisesRegex(SceneError, "padding"):
            self.service.preview(padding=500)


if __name__ == "__main__":
    unittest.main()
