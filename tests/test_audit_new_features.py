"""Unit and integration tests for new features implemented in the feature audit:
Locking, Grouping, Mermaid Conversion, Viewport Control, and Scene Understanding."""

import unittest
from excalidraw_mcp.contracts import GraphCluster, GraphEdge, GraphNode
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.mermaid import parse_mermaid
from excalidraw_mcp.service import SceneService


class LockingAndGroupingTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_lock_and_unlock_elements(self):
        r1 = self.service.add_shape("rectangle", 0, 0, 100, 100, label="Box 1")
        r2 = self.service.add_shape("ellipse", 200, 0, 80, 80, label="Circle 1")

        # Lock r1
        res = self.service.lock_elements([r1["rectangle_id"]])
        self.assertEqual(res["status"], "locked")
        self.assertIn(r1["rectangle_id"], res["element_ids"])
        self.assertIn(r1["label_id"], res["element_ids"])

        doc = self.service.state.document()
        index = {el["id"]: el for el in doc["elements"]}
        self.assertTrue(index[r1["rectangle_id"]]["locked"])
        self.assertTrue(index[r1["label_id"]]["locked"])
        self.assertFalse(index[r2["circle_id"]]["locked"])

        # Mutating locked element should fail
        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.move(r1["rectangle_id"], 50, 50)

        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.resize(r1["rectangle_id"], 150, 150)

        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.update_element(r1["rectangle_id"], stroke_color="#e03131")

        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.delete(r1["rectangle_id"])

        # r2 can still be moved
        move_res = self.service.move(r2["circle_id"], 250, 10)
        self.assertEqual(move_res["status"], "moved")

        # Unlock r1
        unres = self.service.unlock_elements([r1["rectangle_id"]])
        self.assertEqual(unres["status"], "unlocked")
        doc_after = self.service.state.document()
        index_after = {el["id"]: el for el in doc_after["elements"]}
        self.assertFalse(index_after[r1["rectangle_id"]]["locked"])
        self.assertFalse(index_after[r1["label_id"]]["locked"])

        # Now r1 can be moved and deleted
        self.service.move(r1["rectangle_id"], 10, 10)
        del_res = self.service.delete(r1["rectangle_id"])
        self.assertEqual(del_res["status"], "deleted")

    def test_grouping_and_group_aware_movement(self):
        r1 = self.service.add_shape("rectangle", 0, 0, 100, 100)
        r2 = self.service.add_shape("rectangle", 150, 0, 100, 100)
        r3 = self.service.add_shape("rectangle", 300, 0, 100, 100)

        # Group r1 and r2
        grp_res = self.service.group_elements([r1["rectangle_id"], r2["rectangle_id"]])
        self.assertEqual(grp_res["status"], "grouped")
        group_id = grp_res["group_id"]

        doc = self.service.state.document()
        index = {el["id"]: el for el in doc["elements"]}
        self.assertIn(group_id, index[r1["rectangle_id"]]["groupIds"])
        self.assertIn(group_id, index[r2["rectangle_id"]]["groupIds"])
        self.assertEqual(index[r3["rectangle_id"]]["groupIds"], [])

        # Move r1 by (20, 30) -> r1 new position (20, 30), r2 should also move by (20, 30) to (170, 30)!
        self.service.move(r1["rectangle_id"], 20, 30)
        doc = self.service.state.document()
        index = {el["id"]: el for el in doc["elements"]}
        self.assertEqual((index[r1["rectangle_id"]]["x"], index[r1["rectangle_id"]]["y"]), (20, 30))
        self.assertEqual((index[r2["rectangle_id"]]["x"], index[r2["rectangle_id"]]["y"]), (170, 30))
        self.assertEqual((index[r3["rectangle_id"]]["x"], index[r3["rectangle_id"]]["y"]), (300, 0))

        # Ungroup
        ungrp_res = self.service.ungroup_elements(group_id=group_id)
        self.assertEqual(ungrp_res["status"], "ungrouped")
        doc = self.service.state.document()
        index = {el["id"]: el for el in doc["elements"]}
        self.assertNotIn(group_id, index[r1["rectangle_id"]]["groupIds"])
        self.assertNotIn(group_id, index[r2["rectangle_id"]]["groupIds"])

    def test_group_locked_element_prevents_group_move(self):
        r1 = self.service.add_shape("rectangle", 0, 0, 50, 50)
        r2 = self.service.add_shape("rectangle", 100, 0, 50, 50)
        self.service.group_elements([r1["rectangle_id"], r2["rectangle_id"]])
        self.service.lock_elements([r2["rectangle_id"]])

        # Trying to move r1 should fail because its group sibling r2 is locked!
        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.move(r1["rectangle_id"], 10, 10)

    def test_batch_mutate_with_locking_and_grouping(self):
        ops = [
            {"action": "add_rectangle", "client_id": "box1", "x": 0, "y": 0, "w": 100, "h": 50},
            {"action": "add_rectangle", "client_id": "box2", "x": 150, "y": 0, "w": 100, "h": 50},
            {"action": "group", "element_ids": ["box1", "box2"]},
            {"action": "lock", "element_ids": ["box1"]},
        ]
        res = self.service.batch_mutate(ops)
        self.assertEqual(res["status"], "batch executed")
        self.assertEqual(res["operations_executed"], 4)

        b1_id = res["ref_map"]["box1"]
        b2_id = res["ref_map"]["box2"]

        doc = self.service.state.document()
        index = {el["id"]: el for el in doc["elements"]}
        self.assertTrue(index[b1_id]["locked"])
        self.assertFalse(index[b2_id]["locked"])
        self.assertTrue(len(index[b1_id]["groupIds"]) > 0)
        self.assertEqual(index[b1_id]["groupIds"], index[b2_id]["groupIds"])

        # Mutation on locked element in batch should fail atomically
        fail_ops = [
            {"action": "move", "element_id": b1_id, "x": 50, "y": 50}
        ]
        with self.assertRaisesRegex(SceneError, "locked"):
            self.service.batch_mutate(fail_ops)


class MermaidConversionTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_parse_mermaid_basic(self):
        code = """
        flowchart TD
            A[Start] --> B{Decide}
            B -->|Yes| C((Finish))
            B -->|No| D[(Storage)]
        """
        nodes, edges, clusters, direction, layout = parse_mermaid(code)
        self.assertEqual(direction, "vertical")
        self.assertEqual(len(nodes), 4)
        node_map = {n.id: n for n in nodes}
        self.assertEqual(node_map["A"].label, "Start")
        self.assertEqual(node_map["A"].shape, "rectangle")
        self.assertEqual(node_map["B"].label, "Decide")
        self.assertEqual(node_map["B"].shape, "diamond")
        self.assertEqual(node_map["C"].label, "Finish")
        self.assertEqual(node_map["C"].shape, "ellipse")
        self.assertEqual(node_map["D"].label, "Storage")
        self.assertEqual(node_map["D"].shape, "rectangle")

        self.assertEqual(len(edges), 3)
        self.assertEqual(edges[0].source, "A")
        self.assertEqual(edges[0].target, "B")
        self.assertEqual(edges[1].label, "Yes")
        self.assertEqual(edges[2].label, "No")

    def test_parse_mermaid_subgraphs(self):
        code = """
        graph LR
            subgraph Cluster1 [Frontend Layer]
                UI[Web App] --> API[Client API]
            end
            subgraph Cluster2 [Backend Layer]
                SRV[Microservice] --> DB[(Database)]
            end
            API --> SRV
        """
        nodes, edges, clusters, direction, layout = parse_mermaid(code)
        self.assertEqual(direction, "horizontal")
        self.assertEqual(len(clusters), 2)
        cluster_labels = {c.id: c.label for c in clusters}
        self.assertEqual(cluster_labels["Cluster1"], "Frontend Layer")
        self.assertEqual(cluster_labels["Cluster2"], "Backend Layer")

        node_map = {n.id: n for n in nodes}
        self.assertEqual(node_map["UI"].cluster, "Cluster1")
        self.assertEqual(node_map["API"].cluster, "Cluster1")
        self.assertEqual(node_map["SRV"].cluster, "Cluster2")
        self.assertEqual(node_map["DB"].cluster, "Cluster2")

    def test_draw_mermaid_end_to_end(self):
        code = """
        flowchart LR
            User --> Web[Web Frontend]
            Web --> App[Application Server]
            App --> DB[(Database)]
        """
        result = self.service.draw_mermaid(code, elbowed=True)
        self.assertEqual(result["status"], "graph drawn")
        self.assertEqual(result["nodes"], 4)
        self.assertEqual(result["edges"], 3)
        doc = self.service.state.document()
        self.assertGreater(len(doc["elements"]), 0)

    def test_draw_mermaid_with_subgraphs_creates_frames(self):
        code = """
        graph TD
            subgraph VPC [Main VPC]
                S1[Service 1] --> S2[Service 2]
            end
        """
        result = self.service.draw_mermaid(code)
        self.assertEqual(result["status"], "graph drawn")
        self.assertIn("cluster_map", result)
        doc = self.service.state.document()
        types = [el["type"] for el in doc["elements"]]
        self.assertIn("frame", types)

    def test_mermaid_empty_code_raises_error(self):
        with self.assertRaisesRegex(SceneError, "cannot be empty"):
            self.service.draw_mermaid("   ")

        with self.assertRaisesRegex(SceneError, "No valid nodes"):
            self.service.draw_mermaid("graph TD\n%% only comments")


class ViewportControlTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_get_and_set_viewport(self):
        initial = self.service.get_viewport()
        self.assertEqual(initial["scroll_x"], 0.0)
        self.assertEqual(initial["scroll_y"], 0.0)
        self.assertEqual(initial["zoom"], 1.0)
        self.assertEqual(initial["view_background_color"], "#ffffff")

        # Set viewport
        updated = self.service.set_viewport(
            scroll_x=120.5,
            scroll_y=-45.0,
            zoom=1.5,
            background_color="#1e1e1e",
        )
        self.assertEqual(updated["scroll_x"], 120.5)
        self.assertEqual(updated["scroll_y"], -45.0)
        self.assertEqual(updated["zoom"], 1.5)
        self.assertEqual(updated["view_background_color"], "#1e1e1e")

        # Verify get_viewport reads back the same values
        vp = self.service.get_viewport()
        self.assertEqual(vp["scroll_x"], 120.5)
        self.assertEqual(vp["scroll_y"], -45.0)
        self.assertEqual(vp["zoom"], 1.5)
        self.assertEqual(vp["view_background_color"], "#1e1e1e")

    def test_set_viewport_validates_inputs(self):
        with self.assertRaisesRegex(SceneError, "zoom"):
            self.service.set_viewport(zoom=-1.0)

        with self.assertRaisesRegex(SceneError, "hex color"):
            self.service.set_viewport(background_color="not-a-color")

    def test_focus_elements(self):
        self.service.add_shape("rectangle", 100, 100, 200, 100)
        self.service.add_shape("rectangle", 500, 500, 100, 100)

        res = self.service.focus_elements(padding=50)
        self.assertEqual(res["status"], "focused")
        self.assertIn("bounding_box", res)
        self.assertEqual(res["bounding_box"]["x"], 100.0)
        self.assertEqual(res["bounding_box"]["y"], 100.0)
        self.assertGreater(res["zoom"], 0)


class SceneUnderstandingTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_get_scene_summary(self):
        r1 = self.service.add_shape("rectangle", 0, 0, 100, 50, label="Box A")
        r2 = self.service.add_shape("diamond", 200, 0, 100, 50, label="Box B")
        self.service.connect(r1["rectangle_id"], r2["diamond_id"], label="Flows To")
        f = self.service.add_frame("System Boundary", 0, 0, 400, 200, element_ids=[r1["rectangle_id"]])
        self.service.group_elements([r1["rectangle_id"], r2["diamond_id"]])

        summary = self.service.get_scene_summary()
        self.assertIn("element_count", summary)
        self.assertGreater(summary["element_count"], 0)
        self.assertEqual(summary["type_counts"]["rectangle"], 1)
        self.assertEqual(summary["type_counts"]["diamond"], 1)
        self.assertEqual(summary["type_counts"]["arrow"], 1)
        self.assertEqual(summary["type_counts"]["frame"], 1)

        self.assertEqual(len(summary["frames"]), 1)
        self.assertEqual(summary["frames"][0]["name"], "System Boundary")
        self.assertIn(r1["rectangle_id"], summary["frames"][0]["children_ids"])

        self.assertEqual(len(summary["groups"]), 1)
        self.assertEqual(len(summary["connectors"]), 1)
        self.assertEqual(summary["connectors"][0]["source"], r1["rectangle_id"])
        self.assertEqual(summary["connectors"][0]["target"], r2["diamond_id"])
        self.assertEqual(summary["connectors"][0]["label"], "Flows To")

        self.assertIsNotNone(summary["bounds"])
        self.assertIn("Scene (revision", summary["description"])
        self.assertIn("System Boundary", summary["description"])


class MCPProtocolIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_mcp_tools_end_to_end(self):
        from excalidraw_mcp.server import create_server
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}

        # 1. Add rectangles
        r1 = tools["add_rectangle"](x=10, y=10, w=100, h=50, label="Service 1")
        r2 = tools["add_rectangle"](x=200, y=10, w=100, h=50, label="Service 2")
        r1_id = r1["rectangle_id"]
        r2_id = r2["rectangle_id"]

        # 2. Group
        grp = tools["group_elements"](element_ids=[r1_id, r2_id])
        self.assertEqual(grp["status"], "grouped")
        gid = grp["group_id"]

        # 3. Lock r1
        locked = tools["lock_elements"](element_ids=[r1_id])
        self.assertEqual(locked["status"], "locked")

        # 4. Viewport
        vp = tools["get_viewport"]()
        self.assertEqual(vp["zoom"], 1.0)
        set_vp = tools["set_viewport"](zoom=2.0, background_color="#f8f9fa")
        self.assertEqual(set_vp["zoom"], 2.0)
        self.assertEqual(set_vp["view_background_color"], "#f8f9fa")

        # 5. Focus
        foc = tools["focus_elements"](element_ids=[r1_id, r2_id])
        self.assertEqual(foc["status"], "focused")
        self.assertIn("bounding_box", foc)

        # 6. Scene summary
        summary = tools["get_scene_summary"]()
        self.assertGreaterEqual(summary["element_count"], 2)
        self.assertEqual(len(summary["groups"]), 1)

        # 7. Unlock r1
        unl = tools["unlock_elements"](element_ids=[r1_id])
        self.assertEqual(unl["status"], "unlocked")

        # 8. Ungroup
        ungrp = tools["ungroup_elements"](group_id=gid)
        self.assertEqual(ungrp["status"], "ungrouped")

        # 9. Mermaid
        m_res = tools["draw_mermaid"](mermaid_code="graph TD\nClient --> Server")
        self.assertEqual(m_res["status"], "graph drawn")
        self.assertEqual(m_res["nodes"], 2)



if __name__ == "__main__":
    unittest.main()
