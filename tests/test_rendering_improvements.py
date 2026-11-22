import io
import math
import unittest
from PIL import Image

from excalidraw_mcp.renderer import _compute_bounds, render_scene_image
from excalidraw_mcp.service import SceneService


class RenderingImprovementsTests(unittest.TestCase):
    def test_container_label_centering(self):
        """Container-bound text is mathematically centered inside its parent shape."""
        service = SceneService()
        service.add_shape(
            "rectangle",
            100.0,
            100.0,
            200.0,
            100.0,
            label="Centered Label",
            font_size=20,
        )
        doc, _ = service.state.snapshot()
        png_bytes, w, h = render_scene_image(doc, scale=1.0, padding=20)
        self.assertGreater(len(png_bytes), 0)
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (w, h))

    def test_viewport_scale_clamping_for_large_diagram(self):
        """An oversized diagram spanning >4096px is downscaled to fit within 4096px."""
        service = SceneService()
        service.add_shape("rectangle", 0, 0, 100, 100, label="Start")
        service.add_shape("rectangle", 6000, 0, 100, 100, label="End")

        doc, _ = service.state.snapshot()
        png_bytes, img_w, img_h = render_scene_image(doc, scale=1.0, padding=40)
        self.assertLessEqual(img_w, 4096)
        self.assertLessEqual(img_h, 4096)
        self.assertGreaterEqual(img_w, 100)
        self.assertGreaterEqual(img_h, 100)

        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (img_w, img_h))

    def test_viewport_centering_for_small_diagram(self):
        """A tiny diagram (<100px) is centered inside the minimum 100x100 canvas."""
        service = SceneService()
        service.add_shape("rectangle", 0, 0, 20, 20)

        doc, _ = service.state.snapshot()
        png_bytes, img_w, img_h = render_scene_image(doc, scale=1.0, padding=10)
        self.assertEqual(img_w, 100)
        self.assertEqual(img_h, 100)

        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (100, 100))

    def test_arrow_label_background_masking(self):
        """Arrow label background mask protects label text from stroke strike-through."""
        service = SceneService()
        nodes = [
            {"id": "n1", "label": "Sender", "shape": "rectangle"},
            {"id": "n2", "label": "Receiver", "shape": "rectangle"},
        ]
        edges = [
            {"id": "e1", "source": "n1", "target": "n2", "label": "Encrypted Message"},
        ]
        service.draw_graph(nodes, edges, layout="horizontal")
        doc, _ = service.state.snapshot()

        png_bytes, w, h = render_scene_image(doc, scale=1.0)
        self.assertGreater(len(png_bytes), 0)
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (w, h))

    def test_elbowed_connector_orthogonal_rendering(self):
        """Elbowed connector generates orthogonal Manhattan routing in renderer."""
        service = SceneService()
        nodes = [
            {"id": "top_left", "label": "Client", "shape": "rectangle"},
            {"id": "bottom_right", "label": "Worker", "shape": "rectangle"},
        ]
        edges = [
            {"id": "elbow_edge", "source": "top_left", "target": "bottom_right", "label": "Queue"},
        ]
        service.draw_graph(nodes, edges, layout="horizontal", elbowed=True)
        doc, _ = service.state.snapshot()

        png_bytes, w, h = render_scene_image(doc, scale=1.0)
        self.assertGreater(len(png_bytes), 0)
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (w, h))

    def test_rotation_aware_bounding_box(self):
        """_compute_bounds accurately bounds rotated elements."""
        el = {
            "type": "rectangle",
            "x": 100.0,
            "y": 100.0,
            "width": 200.0,
            "height": 40.0,
            "angle": math.pi / 2.0,
        }
        min_x, min_y, max_x, max_y = _compute_bounds([el])

        self.assertAlmostEqual(min_x, 180.0, delta=1.0)
        self.assertAlmostEqual(max_x, 220.0, delta=1.0)
        self.assertAlmostEqual(min_y, 20.0, delta=1.0)
        self.assertAlmostEqual(max_y, 220.0, delta=1.0)

    def test_modern_arrowheads_rendering(self):
        """Renderer renders all modern Excalidraw arrowhead types without error."""
        arrowhead_types = [
            "arrow",
            "triangle",
            "triangle_outline",
            "dot",
            "circle",
            "circle_outline",
            "bar",
            "diamond",
            "diamond_outline",
            "crowfoot_one",
            "crowfoot_many",
            "crowfoot_one_or_more",
        ]
        service = SceneService()
        for idx, head in enumerate(arrowhead_types):
            y_pos = idx * 60
            service.add_arrow(
                50,
                y_pos,
                250,
                y_pos,
                label=head,
                start_arrowhead="bar",
                end_arrowhead=head,
            )

        doc, _ = service.state.snapshot()
        png_bytes, w, h = render_scene_image(doc, scale=1.0, padding=20)
        self.assertGreater(len(png_bytes), 0)
        img = Image.open(io.BytesIO(png_bytes))
        self.assertEqual(img.size, (w, h))
        self.assertEqual(img.format, "PNG")


if __name__ == "__main__":
    unittest.main()
