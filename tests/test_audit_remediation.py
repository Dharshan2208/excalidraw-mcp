"""Verification and regression test suite for audit remediations.

Validates security confinement, MCP contract alignments, parser enhancements,
live server thread safety/bind failure handling, and geometry edge cases.
"""

import logging
import os
import socket
import tempfile
import unittest

from excalidraw_mcp.contracts import BatchOperation
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.importer import parse_scene_payload
from excalidraw_mcp.live_server import LiveCanvasServer
from excalidraw_mcp.mermaid import parse_mermaid
from excalidraw_mcp.service import SceneService


class AuditRemediationTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def tearDown(self):
        try:
            self.service.stop_live_server()
        except Exception:
            pass

    def test_importer_path_traversal_protection(self):
        """Ensure importer rejects arbitrary system paths and non-diagram extensions."""
        # Sensitive absolute file path
        if os.path.exists("/etc/passwd"):
            with self.assertRaisesRegex(SceneError, "(outside permitted|denied)"):
                parse_scene_payload("/etc/passwd")

        # Path traversal sequences
        with self.assertRaisesRegex(SceneError, "(outside permitted|denied|Unrecognized)"):
            parse_scene_payload("../../../etc/passwd")

        # Temporary file with valid extension is permitted
        with tempfile.NamedTemporaryFile("w+", suffix=".excalidraw", delete=False) as tf:
            tf.write('{"type": "excalidraw", "version": 2, "elements": []}')
            tf_path = tf.name

        try:
            doc = parse_scene_payload(tf_path)
            self.assertEqual(doc["type"], "excalidraw")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_export_png_directory_confinement(self):
        """Ensure PNG export cannot write into arbitrary system directories."""
        self.service.add_shape("rectangle", 0, 0, 100, 100)
        with self.assertRaisesRegex(SceneError, "outside permitted"):
            self.service.export_png("exploit", directory="/etc")

        # Writing within allowed temp dir works
        with tempfile.TemporaryDirectory() as td:
            res = self.service.export_png("allowed", directory=td)
            self.assertEqual(res["status"], "png exported")
            self.assertTrue(os.path.exists(res["path"]))

    def test_get_scene_summary_code_blocks(self):
        """Ensure get_scene_summary accurately registers code blocks with dynamic line counts."""
        self.service.add_code_block(
            code="def add(a, b):\n    return a + b\n\nprint(add(1, 2))",
            language="python",
            title="Calculator",
        )
        summary = self.service.get_scene_summary()
        self.assertEqual(len(summary["code_blocks"]), 1)
        cb = summary["code_blocks"][0]
        self.assertEqual(cb["language"], "python")
        self.assertEqual(cb["title"], "Calculator")
        self.assertEqual(cb["lines_count"], 4)

    def test_code_block_text_container_alignment(self):
        """Ensure bound text in code block maintains left/top alignment."""
        res = self.service.add_code_block("line 1\nline 2")
        text_el = self.service.state.get(res["text_id"])
        self.assertEqual(text_el["textAlign"], "left")
        self.assertEqual(text_el["verticalAlign"], "top")

    def test_mermaid_multi_node_and_connectors(self):
        """Ensure Mermaid parser handles multi-node branching and joining syntax (A & B --> C & D)."""
        diagram = """graph TD
A & B --> C & D
"""
        nodes, edges, *_ = parse_mermaid(diagram)
        node_ids = {n.id for n in nodes}
        self.assertEqual(node_ids, {"A", "B", "C", "D"})
        self.assertEqual(len(edges), 4)
        edge_pairs = {(e.source, e.target) for e in edges}
        self.assertIn(("A", "C"), edge_pairs)
        self.assertIn(("A", "D"), edge_pairs)
        self.assertIn(("B", "C"), edge_pairs)
        self.assertIn(("B", "D"), edge_pairs)

    def test_batch_operation_code_block_contract(self):
        """Ensure BatchOperation contract schema accepts code block specific fields."""
        op = BatchOperation(
            action="add_code_block",
            code="console.log('hello');",
            language="javascript",
            title="Snippet",
            theme="monokai",
            line_numbers=False,
        )
        self.assertEqual(op.code, "console.log('hello');")
        self.assertEqual(op.language, "javascript")
        self.assertEqual(op.title, "Snippet")
        self.assertEqual(op.theme, "monokai")
        self.assertFalse(op.line_numbers)

    def test_live_server_port_conflict_reporting(self):
        """Ensure live server detects bind failure gracefully without hanging or false positive."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        occupied_port = sock.getsockname()[1]

        server = None
        try:
            server = LiveCanvasServer(self.service)
            # Suppress noisy expected bind error log output from Uvicorn
            uvicorn_logger = logging.getLogger("uvicorn.error")
            prev_level = uvicorn_logger.level
            uvicorn_logger.setLevel(logging.CRITICAL)
            try:
                res = server.start(port=occupied_port)
            finally:
                uvicorn_logger.setLevel(prev_level)
            self.assertEqual(res["status"], "failed")
            self.assertIn("error", res)
            self.assertFalse(server.is_running)
        finally:
            if server:
                server.stop()
            sock.close()

    def test_draw_graph_parallel_edges_offset(self):
        """Ensure multiple edges connecting the same source and target are separated spatially."""
        nodes = [
            {"id": "svc_a", "label": "Service A", "shape": "rectangle"},
            {"id": "svc_b", "label": "Service B", "shape": "rectangle"},
        ]
        edges = [
            {"id": "e_grpc", "source": "svc_a", "target": "svc_b", "label": "gRPC"},
            {"id": "e_http", "source": "svc_a", "target": "svc_b", "label": "HTTP"},
        ]
        res = self.service.draw_graph(nodes, edges, layout="horizontal")
        arrow1 = self.service.state.get(res["edge_map"]["e_grpc"]["element_id"])
        arrow2 = self.service.state.get(res["edge_map"]["e_http"]["element_id"])

        # Compare coordinates: arrows should not share identical starting or ending coordinates
        self.assertNotEqual(arrow1["y"], arrow2["y"])

    def test_library_resource_path_traversal(self):
        """Ensure get_resource for libraries rejects directory traversal sequences."""
        with self.assertRaisesRegex(SceneError, "outside permitted directory"):
            self.service.get_resource(resource_type="library", identifier="../../etc/passwd")

    def test_get_scene_summary_upward_arrow_bounds(self):
        """Ensure get_scene_summary does not clobber point-aware max_y for upward-pointing arrows."""
        # Add an arrow pointing upward from y=300 to y=100
        self.service.add_arrow(100, 300, 200, 100)
        summary = self.service.get_scene_summary()
        self.assertIsNotNone(summary["bounds"])
        self.assertEqual(summary["bounds"]["min_y"], 100)
        self.assertEqual(summary["bounds"]["max_y"], 300)
        self.assertEqual(summary["bounds"]["height"], 200)

    def test_replace_bumps_modified_element_version(self):
        """Ensure replace() increments version and assigns versionNonce on modified elements."""
        res = self.service.add_shape("rectangle", 0, 0, 100, 100)
        rect_id = res["rectangle_id"]
        initial_el = self.service.state.get(rect_id)
        self.assertEqual(initial_el["version"], 1)

        # Mutate width and replace document
        doc = self.service.state.document()
        for el in doc["elements"]:
            if el["id"] == rect_id:
                el["width"] = 250
        self.service.state.replace(doc)

        updated_el = self.service.state.get(rect_id)
        self.assertEqual(updated_el["width"], 250)
        self.assertEqual(updated_el["version"], 2)
        self.assertNotEqual(updated_el["versionNonce"], initial_el["versionNonce"])

    def test_observer_can_query_state_without_deadlock(self):
        """Ensure state observer callbacks execute outside the mutation lock without deadlocking."""
        observed_queries = []

        def on_change(doc, rev):
            # Query the state synchronously within the listener callback
            el = self.service.state.get("observed_box")
            observed_queries.append((rev, el is not None))

        unsub = self.service.state.subscribe(on_change)
        try:
            # Trigger apply / add_shape
            self.service.add_shape("rectangle", 0, 0, 100, 100)
            self.assertGreater(len(observed_queries), 0)

            # Trigger replace
            doc = self.service.state.document()
            doc["elements"].append({
                "id": "observed_box",
                "type": "rectangle",
                "x": 0, "y": 0, "width": 50, "height": 50,
                "angle": 0, "strokeColor": "#000", "backgroundColor": "transparent",
                "fillStyle": "solid", "strokeWidth": 1, "strokeStyle": "solid",
                "roughness": 1, "opacity": 100, "groupIds": [], "roundness": None,
                "seed": 1, "version": 1, "versionNonce": 1, "isDeleted": False,
                "boundElements": [], "updated": 1, "link": None, "locked": False,
            })
            self.service.state.replace(doc)
            self.assertTrue(any(found for _, found in observed_queries))
        finally:
            unsub()

    def test_code_block_title_height_without_title(self):
        """Ensure calculate_code_block_dimensions allocates smaller header when title is omitted."""
        from excalidraw_mcp.code_blocks import calculate_code_block_dimensions

        code = "\n".join(f"var_{i} = {i}" for i in range(10))
        _, h_with_title, _, _ = calculate_code_block_dimensions(code, title="Custom Title")
        _, h_without_title, _, _ = calculate_code_block_dimensions(code, title=None)
        self.assertGreater(h_with_title, h_without_title)

    def test_graph_node_and_edge_individual_styles(self):
        """Ensure draw_graph respects per-node and per-edge custom colors and styles."""
        nodes = [
            {"id": "n1", "label": "Red Node", "backgroundColor": "#ff0000", "strokeColor": "#990000"},
            {"id": "n2", "label": "Green Node", "backgroundColor": "#00ff00", "strokeColor": "#009900"},
        ]
        edges = [
            {"source": "n1", "target": "n2", "strokeColor": "#0000ff", "strokeStyle": "dashed"},
        ]
        res = self.service.draw_graph(nodes, edges)
        node1_el = self.service.state.get(res["node_map"]["n1"]["element_id"])
        node2_el = self.service.state.get(res["node_map"]["n2"]["element_id"])
        edge_id = list(res["edge_map"].values())[0]["element_id"]
        edge_el = self.service.state.get(edge_id)

        self.assertEqual(node1_el["backgroundColor"], "#ff0000")
        self.assertEqual(node1_el["strokeColor"], "#990000")
        self.assertEqual(node2_el["backgroundColor"], "#00ff00")
        self.assertEqual(node2_el["strokeColor"], "#009900")
        self.assertEqual(edge_el["strokeColor"], "#0000ff")
        self.assertEqual(edge_el["strokeStyle"], "dashed")

    def test_batch_mutate_duplicate_elements(self):
        """Ensure batch_mutate supports duplicate action atomically with client_id references."""
        rect = self.service.add_shape("rectangle", 10, 20, 100, 80)
        orig_id = rect["rectangle_id"]

        ops = [
            {
                "action": "duplicate",
                "element_ids": [orig_id],
                "offset_x": 40.0,
                "offset_y": 60.0,
                "client_id": "cloned_box",
            },
            {
                "action": "update_element",
                "element_id": "client:cloned_box",
                "strokeColor": "#e03131",
            },
        ]
        batch_res = self.service.batch_mutate(ops)
        self.assertEqual(batch_res["status"], "batch executed")
        self.assertEqual(batch_res["operations_executed"], 2)

        cloned_id = batch_res["ref_map"]["cloned_box"]
        cloned_el = self.service.state.get(cloned_id)
        self.assertEqual(cloned_el["x"], 50.0)
        self.assertEqual(cloned_el["y"], 80.0)
        self.assertEqual(cloned_el["strokeColor"], "#e03131")

    def test_renderer_dashed_and_dotted_strokes(self):
        """Ensure PNG renderer processes dashed/dotted shapes and connectors cleanly."""
        from excalidraw_mcp.renderer import render_scene_to_png

        self.service.add_shape("rectangle", 0, 0, 100, 80, strokeStyle="dashed")
        self.service.add_shape("diamond", 150, 0, 100, 80, strokeStyle="dotted")
        self.service.add_arrow(50, 80, 200, 80, strokeStyle="dashed")

        doc, _ = self.service.state.snapshot()
        png_bytes = render_scene_to_png(doc)
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
