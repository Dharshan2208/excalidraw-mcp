import asyncio
import io
import json
import os
import socket
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

import httpx
from PIL import Image as PILImage
from starlette.testclient import TestClient

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.importer import parse_scene_payload
from excalidraw_mcp.live_server import LiveCanvasServer
from excalidraw_mcp.renderer import render_scene_to_png
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.sharing import export_to_excalidraw_url


class ElementDuplicationTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_duplicate_single_element(self):
        rect = self.service.add_shape("rectangle", 10, 20, 100, 80)
        res = self.service.duplicate_elements([rect["rectangle_id"]], offset_x=30, offset_y=40)
        self.assertEqual(res["status"], "duplicated")
        self.assertEqual(len(res["duplicated_ids"]), 1)
        cloned_id = res["duplicated_ids"][0]
        self.assertNotEqual(cloned_id, rect["rectangle_id"])

        cloned_elem = self.service.state.get(cloned_id)
        self.assertEqual(cloned_elem["x"], 40)
        self.assertEqual(cloned_elem["y"], 60)
        self.assertEqual(cloned_elem["width"], 100)
        self.assertEqual(cloned_elem["height"], 80)

    def test_duplicate_shape_with_bound_label(self):
        rect = self.service.add_shape("rectangle", 0, 0, 120, 90, label="Process")
        rect_id = rect["rectangle_id"]
        label_id = rect["label_id"]

        res = self.service.duplicate_elements([rect_id], offset_x=50, offset_y=50)
        self.assertEqual(res["status"], "duplicated")
        cloned_rect_id = res["id_mapping"][rect_id]
        cloned_label_id = res["id_mapping"][label_id]

        cloned_rect = self.service.state.get(cloned_rect_id)
        cloned_label = self.service.state.get(cloned_label_id)

        self.assertEqual(cloned_rect["x"], 50)
        self.assertEqual(cloned_rect["y"], 50)
        self.assertIn(cloned_label_id, [b["id"] for b in cloned_rect.get("boundElements", [])])
        self.assertEqual(cloned_label.get("containerId"), cloned_rect_id)
        self.assertEqual(cloned_label["text"], "Process")

    def test_duplicate_connected_arrow_remaps_endpoints(self):
        r1 = self.service.add_shape("rectangle", 0, 0, 100, 50, label="A")
        r2 = self.service.add_shape("rectangle", 200, 0, 100, 50, label="B")
        conn = self.service.connect(r1["rectangle_id"], r2["rectangle_id"], label="Flow")
        arrow_id = conn["arrow_id"]

        res = self.service.duplicate_elements(
            [r1["rectangle_id"], r2["rectangle_id"], arrow_id],
            offset_x=0,
            offset_y=150,
        )

        cloned_r1 = res["id_mapping"][r1["rectangle_id"]]
        cloned_r2 = res["id_mapping"][r2["rectangle_id"]]
        cloned_arrow = res["id_mapping"][arrow_id]

        arrow_elem = self.service.state.get(cloned_arrow)
        self.assertEqual(arrow_elem.get("startBinding", {}).get("elementId"), cloned_r1)
        self.assertEqual(arrow_elem.get("endBinding", {}).get("elementId"), cloned_r2)

    def test_duplicate_group_and_frame_association(self):
        frame = self.service.add_frame("Container", 0, 0, 300, 300)
        frame_id = frame["frame_id"]

        r1 = self.service.add_shape("rectangle", 20, 20, 80, 50, frame_id=frame_id)
        r2 = self.service.add_shape("rectangle", 120, 20, 80, 50, frame_id=frame_id)
        self.service.group_elements([r1["rectangle_id"], r2["rectangle_id"]])

        res = self.service.duplicate_elements(
            [frame_id, r1["rectangle_id"], r2["rectangle_id"]],
            offset_x=400,
            offset_y=0,
        )

        cloned_frame_id = res["id_mapping"][frame_id]
        cloned_r1 = self.service.state.get(res["id_mapping"][r1["rectangle_id"]])
        cloned_r2 = self.service.state.get(res["id_mapping"][r2["rectangle_id"]])

        self.assertEqual(cloned_r1.get("frameId"), cloned_frame_id)
        self.assertEqual(cloned_r2.get("frameId"), cloned_frame_id)

        # Cloned elements should share a new group id distinct from original group
        original_r1 = self.service.state.get(r1["rectangle_id"])
        self.assertNotEqual(cloned_r1["groupIds"], original_r1["groupIds"])
        self.assertEqual(cloned_r1["groupIds"], cloned_r2["groupIds"])

    def test_duplicate_missing_element_raises_error(self):
        with self.assertRaises(SceneError):
            self.service.duplicate_elements(["nonexistent_id"])


class SceneDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_describe_empty_scene(self):
        desc = self.service.describe_scene()
        self.assertEqual(desc["element_count"], 0)
        self.assertIn("Total Elements: 0", desc["summary"])
        self.assertEqual(desc["layout_type"], "freeform")

    def test_describe_complex_scene(self):
        frame = self.service.add_frame("Architecture", 0, 0, 500, 300)
        frame_id = frame["frame_id"]
        r1 = self.service.add_shape("rectangle", 20, 40, 100, 60, label="Frontend", frame_id=frame_id)
        r2 = self.service.add_shape("ellipse", 250, 40, 100, 60, label="Backend", frame_id=frame_id)
        self.service.connect(r1["rectangle_id"], r2["circle_id"], label="HTTPS")

        desc = self.service.describe_scene()
        self.assertGreater(desc["element_count"], 0)
        self.assertIn("Architecture", desc["summary"])
        self.assertIn("HTTPS", desc["summary"])
        self.assertIn("Frontend", desc["summary"])
        self.assertEqual(len(desc["connections"]), 1)
        self.assertEqual(desc["connections"][0]["label"], "HTTPS")
        self.assertIsNotNone(desc["bounds"])


class ExportToExcalidrawUrlTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.service.add_shape("rectangle", 10, 10, 100, 100, label="Test Node")

    @patch("httpx.Client.post")
    def test_export_to_url_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": "test-scene-123"}
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = self.service.export_to_excalidraw_url(verify=False)
        self.assertEqual(result["id"], "test-scene-123")
        self.assertTrue(result["url"].startswith("https://excalidraw.com/#json=test-scene-123,"))
        self.assertEqual(result["status"], "published")

        # Verify POST payload sent to excalidraw API
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://json.excalidraw.com/api/v2/post/")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/octet-stream")

    @patch("httpx.Client.post")
    def test_export_to_url_network_failure(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Network unreachable")
        with self.assertRaises(SceneError) as ctx:
            self.service.export_to_excalidraw_url()
        self.assertIn("Network error while connecting to Excalidraw server", str(ctx.exception))


class CanvasScreenshotTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.service.add_shape("rectangle", 0, 0, 100, 100, label="Box")

    def test_preview_returns_valid_image_with_embedded_metadata(self):
        png_bytes = self.service.preview()
        self.assertTrue(png_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

        # Verify image can be parsed by PIL and has embedded scene metadata
        pil_img = PILImage.open(io.BytesIO(png_bytes))
        self.assertEqual(pil_img.format, "PNG")
        self.assertIn("application/vnd.excalidraw+json", pil_img.info)
        embedded_doc = json.loads(pil_img.info["application/vnd.excalidraw+json"])
        self.assertIn("elements", embedded_doc)
        self.assertEqual(len(embedded_doc["elements"]), 2)  # Rectangle + label

    def test_server_get_canvas_screenshot_tool(self):
        server = create_server(self.service, toolset="full")
        tools = {tool.name: tool.fn for tool in asyncio.run(server.list_tools())}
        img = tools["get_canvas_screenshot"]()
        self.assertTrue(img.data.startswith(b"\x89PNG\r\n\x1a\n"))
        pil_img = PILImage.open(io.BytesIO(img.data))
        self.assertIn("application/vnd.excalidraw+json", pil_img.info)
        embedded_doc = json.loads(pil_img.info["application/vnd.excalidraw+json"])
        self.assertIn("elements", embedded_doc)
        self.assertEqual(len(embedded_doc["elements"]), 2)  # Rectangle + label


class GenericResourceAccessTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.service.add_shape("rectangle", 0, 0, 50, 50, label="A")

    def test_get_current_scene_resource(self):
        res = self.service.get_resource(uri="excalidraw://scene")
        self.assertEqual(res["resource_type"], "scene")
        self.assertEqual(len(res["document"]["elements"]), 2)

    def test_get_saved_scene_resource(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.dict(os.environ, {"EXCALIDRAW_SCENE_DIR": td}):
                self.service.save("my_saved_diagram")
                res = self.service.get_resource(uri="excalidraw://scenes/my_saved_diagram")
                self.assertEqual(res["resource_type"], "scene")
                self.assertEqual(res["identifier"], "my_saved_diagram")

    def test_get_library_resources(self):
        res = self.service.get_resource(uri="excalidraw://libraries/architecture")
        self.assertEqual(res["resource_type"], "library")
        self.assertEqual(res["library"]["name"], "architecture")
        self.assertGreater(len(res["library"]["items"]), 0)

        # Explicit parameter access
        res2 = self.service.get_resource(resource_type="library", identifier="flowchart")
        self.assertEqual(res2["resource_type"], "library")
        self.assertEqual(res2["library"]["name"], "flowchart")
        self.assertGreater(len(res2["library"]["items"]), 0)

    def test_get_theme_resources(self):
        res = self.service.get_resource(uri="excalidraw://themes/nord")
        self.assertEqual(res["resource_type"], "theme")
        self.assertEqual(res["theme"]["name"], "nord")
        self.assertIn("palette", res["theme"])

    def test_get_element_resource(self):
        doc = self.service.state.document()
        elem_id = doc["elements"][0]["id"]
        res = self.service.get_resource(uri=f"excalidraw://elements/{elem_id}")
        self.assertEqual(res["resource_type"], "element")
        self.assertEqual(res["element"]["id"], elem_id)

    def test_invalid_resource_errors(self):
        with self.assertRaisesRegex(SceneError, "Invalid resource URI"):
            self.service.get_resource(uri="invalid://something")

        with self.assertRaisesRegex(SceneError, "Theme 'unknown_theme' not found"):
            self.service.get_resource(resource_type="theme", identifier="unknown_theme")


class DiagramDesignGuideTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_read_full_diagram_guide(self):
        guide = self.service.read_diagram_guide()
        self.assertEqual(guide["topic"], "all")
        self.assertIn("layout", guide["guide"])
        self.assertIn("colors", guide["guide"])
        self.assertGreater(len(guide["available_topics"]), 5)

    def test_read_topic_guides(self):
        for topic in ["layout", "colors", "typography", "grouping", "arrows", "spacing"]:
            guide = self.service.read_diagram_guide(topic=topic)
            self.assertEqual(guide["topic"], topic)
            self.assertIn("title", guide["guide"])
            self.assertIn("principles", guide["guide"])

    def test_invalid_topic_guide(self):
        with self.assertRaisesRegex(SceneError, "Unknown topic"):
            self.service.read_diagram_guide(topic="not_a_topic")


class SceneImportTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_import_raw_json_replace(self):
        raw_json = json.dumps({
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": "node-1", "type": "rectangle", "x": 100, "y": 100, "width": 80, "height": 40}
            ],
            "appState": {"viewBackgroundColor": "#fafafa"}
        })
        res = self.service.import_scene(data=raw_json, mode="replace")
        self.assertEqual(res["mode"], "replace")
        self.assertEqual(res["elements_imported"], 1)
        self.assertEqual(self.service.state.all()[0]["id"], "node-1")
        self.assertEqual(self.service.state.document()["appState"]["viewBackgroundColor"], "#fafafa")

    def test_import_excalidraw_file_merge_with_collision_remap(self):
        self.service.add_shape("rectangle", 0, 0, 50, 50, label="Existing")
        existing_id = self.service.state.all()[0]["id"]

        scene_dict = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": existing_id, "type": "ellipse", "x": 10, "y": 20, "width": 60, "height": 60}
            ]
        }
        with tempfile.NamedTemporaryFile("w+", suffix=".excalidraw", delete=False) as tf:
            tf.write(json.dumps(scene_dict))
            tf_path = tf.name

        try:
            res = self.service.import_scene(data=tf_path, mode="merge", offset_x=100, offset_y=100)
            self.assertEqual(res["mode"], "merge")
            self.assertEqual(res["elements_imported"], 1)
            # Conflicting ID was remapped
            self.assertIn(existing_id, res["id_mapping"])
            new_id = res["id_mapping"][existing_id]
            new_elem = self.service.state.get(new_id)
            self.assertEqual(new_elem["x"], 110)
            self.assertEqual(new_elem["y"], 120)
            # Total elements is original (rect + label) + 1 new ellipse = 3
            self.assertEqual(len(self.service.state.all()), 3)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_import_obsidian_markdown(self):
        obsidian_content = """# Diagram Document
Some notes before diagram.

# Excalidraw Data
```json
{
  "type": "excalidraw",
  "version": 2,
  "elements": [
    {"id": "obsidian-1", "type": "diamond", "x": 50, "y": 50, "width": 40, "height": 40}
  ]
}
```
"""
        with tempfile.NamedTemporaryFile("w+", suffix=".excalidraw.md", delete=False) as tf:
            tf.write(obsidian_content)
            tf_path = tf.name

        try:
            res = self.service.import_scene(data=tf_path, mode="replace")
            self.assertEqual(res["elements_imported"], 1)
            self.assertEqual(self.service.state.all()[0]["type"], "diamond")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_import_png_embedded_metadata(self):
        # Render a scene to PNG
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": "png-elem", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 80}
            ]
        }
        png_bytes = render_scene_to_png(doc)

        with tempfile.NamedTemporaryFile("wb", suffix=".png", delete=False) as tf:
            tf.write(png_bytes)
            tf_path = tf.name

        try:
            res = self.service.import_scene(data=tf_path, mode="replace")
            self.assertEqual(res["elements_imported"], 1)
            self.assertEqual(self.service.state.all()[0]["id"], "png-elem")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    def test_import_invalid_data(self):
        with self.assertRaisesRegex(SceneError, "Import data cannot be empty"):
            self.service.import_scene(data="")

        with self.assertRaisesRegex(SceneError, "Unrecognized import format"):
            self.service.import_scene(data="not-json")


class LiveCanvasServerTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()
        self.server = LiveCanvasServer(self.service)
        self.client = TestClient(self.server.app)

    def tearDown(self):
        try:
            self.service.stop_live_server()
        except Exception:
            pass
        try:
            self.server.stop()
        except Exception:
            pass

    def test_root_canvas_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("<!DOCTYPE html>", response.text)
        self.assertIn("Excalidraw Live Canvas", response.text)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["element_count"], 0)

    def test_scene_get_and_post(self):
        # GET empty scene
        resp = self.client.get("/api/scene")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["elements"], [])

        # POST updated scene
        new_scene = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": "sync-1", "type": "rectangle", "x": 0, "y": 0, "width": 50, "height": 50}
            ]
        }
        post_resp = self.client.post("/api/scene", json=new_scene)
        self.assertEqual(post_resp.status_code, 200)
        self.assertEqual(post_resp.json()["status"], "updated")
        self.assertEqual(len(self.service.state.all()), 1)

    def test_screenshot_endpoint(self):
        self.service.add_shape("rectangle", 0, 0, 60, 60, label="Box")
        resp = self.client.get("/api/screenshot")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.headers["content-type"], "image/png")
        self.assertTrue(resp.content.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_websocket_sync(self):
        with self.client.websocket_connect("/ws") as websocket:
            initial = websocket.receive_json()
            self.assertEqual(initial["type"], "init")

            # Client sends scene update
            websocket.send_json({
                "type": "update",
                "scene": {
                    "type": "excalidraw",
                    "version": 2,
                    "elements": [
                        {"id": "ws-node", "type": "diamond", "x": 10, "y": 10, "width": 50, "height": 50}
                    ]
                }
            })
            # Verify backend updated (allow small async event propagation window)
            for _ in range(30):
                if self.service.state.all():
                    break
                time.sleep(0.01)
            self.assertEqual(self.service.state.all()[0]["id"], "ws-node")

    def test_service_live_server_lifecycle(self):
        status1 = self.service.get_live_server_status()
        self.assertFalse(status1["is_running"])

        # Dynamically allocate an open port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            free_port = s.getsockname()[1]

        start_res = self.service.start_live_server(port=free_port)
        self.assertEqual(start_res["status"], "started")
        self.assertEqual(start_res["port"], free_port)
        self.assertIn(f"http://127.0.0.1:{free_port}", start_res["url"])

        # Calling start again returns current running status
        start_again = self.service.start_live_server(port=free_port)
        self.assertEqual(start_again["status"], "already_running")

        status2 = self.service.get_live_server_status()
        self.assertTrue(status2["is_running"])

        stop_res = self.service.stop_live_server()
        self.assertEqual(stop_res["status"], "stopped")


if __name__ == "__main__":
    unittest.main()
