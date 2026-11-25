import math
import unittest

from excalidraw_mcp.elements import rect, text
from excalidraw_mcp.fonts import get_font, measure_text_dimensions
from excalidraw_mcp.layout import shape_dimensions, wrap_text_to_shape
from excalidraw_mcp.service import SceneService


class TextContainmentTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_measure_text_dimensions_accuracy(self):
        """Accurate FreeType/Pillow measurement returns realistic dimensions."""
        w, h, line_widths = measure_text_dimensions("Short text", font_family=2, font_size=20)
        self.assertGreater(w, 50.0)
        self.assertLess(w, 150.0)
        self.assertGreaterEqual(h, 25.0)
        self.assertEqual(len(line_widths), 1)

        # Multiline text
        w_multi, h_multi, lines = measure_text_dimensions("Line 1\nMuch Longer Line 2", font_family=2, font_size=20)
        self.assertGreater(w_multi, w)
        self.assertGreater(h_multi, h)
        self.assertEqual(len(lines), 2)

    def test_wrap_text_to_shape_respects_shape_boundaries(self):
        """wrap_text_to_shape breaks long strings into lines that fit safe widths."""
        long_text = "This is a comprehensive description of the authentication and authorization gateway service"
        wrapped = wrap_text_to_shape(long_text, shape="rectangle", target_w=200, font_size=20)
        lines = wrapped.splitlines()
        self.assertGreater(len(lines), 1)
        for line in lines:
            lw, _, _ = measure_text_dimensions(line, font_size=20)
            # Safe width for 200px rectangle with 20px padding is 160px
            # Individual wrapped line width should reasonably fit within safe bounds
            self.assertLess(lw, 260.0)

    def test_shape_dimensions_scales_with_font_size(self):
        """shape_dimensions produces larger containers for larger font sizes."""
        label = "Microservice Node Architecture\nDetailed Processing Pipeline"
        w_small, h_small = shape_dimensions("rectangle", label, font_size=14)
        w_med, h_med = shape_dimensions("rectangle", label, font_size=20)
        w_large, h_large = shape_dimensions("rectangle", label, font_size=36)

        self.assertLess(w_small, w_med)
        self.assertLess(w_med, w_large)
        self.assertLess(h_small, h_med)
        self.assertLess(h_med, h_large)

    def test_diamond_rhombus_containment_inscribed_geometry(self):
        """All four corners of a diamond's text block must be strictly within rhombus boundary."""
        for label in [
            "Decision",
            "Evaluate User Auth & Tokens",
            "Multi-step Gateway Condition Check",
        ]:
            w, h = shape_dimensions("diamond", label, font_size=20)
            wrapped = wrap_text_to_shape(label, shape="diamond", target_w=w, font_size=20)
            tw, th, _ = measure_text_dimensions(wrapped, font_size=20)

            # Inscribed rhombus boundary test: (tw / w) + (th / h) <= 1.0
            corner_ratio = (tw / w) + (th / h)
            self.assertLess(
                corner_ratio,
                1.0,
                f"Label '{label}' text corners overflow diamond: ratio {corner_ratio:.3f} > 1.0",
            )

    def test_ellipse_containment_inscribed_geometry(self):
        """All four corners of an ellipse's text block must lie strictly inside ellipse radius."""
        for label in [
            "Start State",
            "Background Event Queue Worker Process",
            "Distributed Event Store",
        ]:
            w, h = shape_dimensions("ellipse", label, font_size=20)
            wrapped = wrap_text_to_shape(label, shape="ellipse", target_w=w, font_size=20)
            tw, th, _ = measure_text_dimensions(wrapped, font_size=20)

            # Inscribed ellipse boundary test: (tw/w)^2 + (th/h)^2 <= 0.5 (for circle corner test)
            corner_dist = math.hypot(tw / 2.0, th / 2.0)
            radius = min(w, h) / 2.0
            self.assertLess(
                corner_dist,
                radius,
                f"Label '{label}' text corners overflow ellipse radius: corner {corner_dist:.1f} >= radius {radius:.1f}",
            )

    def test_add_shape_auto_wraps_long_label(self):
        """add_shape automatically wraps long text so it doesn't span a single massive line."""
        res = self.service.add_shape(
            "rectangle",
            100,
            100,
            180,
            80,
            label="Very Long Service Description That Previously Extended Past The Box",
        )
        label_el = self.service.state.get(res["label_id"])
        self.assertIn("\n", label_el["text"])

        # Container should also have expanded to fit the multiline text comfortably
        rect_el = self.service.state.get(res["rectangle_id"])
        self.assertGreaterEqual(rect_el["width"], 180)
        self.assertGreater(rect_el["height"], 80)

    def test_update_element_auto_expands_container_outward(self):
        """Updating a shape with a longer label expands the container outward from its center."""
        res = self.service.add_shape("rectangle", 200, 200, 180, 80, label="Initial")
        rect_before = self.service.state.get(res["rectangle_id"])
        center_before = (
            rect_before["x"] + rect_before["width"] / 2.0,
            rect_before["y"] + rect_before["height"] / 2.0,
        )

        # Update with a much longer label
        self.service.update_element(
            res["rectangle_id"],
            label="Significantly Expanded Multi-Tier Architecture Processing Subsystem",
        )
        rect_after = self.service.state.get(res["rectangle_id"])
        center_after = (
            rect_after["x"] + rect_after["width"] / 2.0,
            rect_after["y"] + rect_after["height"] / 2.0,
        )

        # Shape expanded (height grows for wrapped lines; width stays >= original)
        self.assertGreaterEqual(rect_after["width"], rect_before["width"])
        self.assertGreater(rect_after["height"], rect_before["height"])

        # Center point was preserved (within floating point precision)
        self.assertAlmostEqual(center_before[0], center_after[0], places=1)
        self.assertAlmostEqual(center_before[1], center_after[1], places=1)

    def test_connectors_attach_to_expanded_shape_boundaries(self):
        """Connectors reroute cleanly to outer boundary of auto-expanded shapes."""
        r1 = self.service.add_shape(
            "rectangle",
            100,
            100,
            100,
            60,
            label="Super Extended Source Node Name With Multiline Text",
        )
        r2 = self.service.add_shape("rectangle", 500, 100, 120, 60, label="Target Node")
        conn = self.service.connect(r1["rectangle_id"], r2["rectangle_id"])

        connector_el = self.service.state.get(conn["arrow_id"])
        rect1_el = self.service.state.get(r1["rectangle_id"])

        # Connector start point x should be at or near rect1's right edge, not its initial 100+100=200
        start_world_x = connector_el["x"] + connector_el["points"][0][0]
        rect1_right_edge = rect1_el["x"] + rect1_el["width"]
        self.assertAlmostEqual(start_world_x, rect1_right_edge, delta=5.0)

    def test_unicode_and_cjk_containment(self):
        """Unicode characters (e.g., CJK) are accommodated with sufficient width."""
        w, h = shape_dimensions("rectangle", "日本語認証サーバー", font_size=20)
        self.assertGreater(w, 180.0)
        self.assertGreater(h, 60.0)

    def test_add_text_uses_actual_font_metrics(self):
        """Regression for BUG-010: text() must use measure_text_dimensions, not 0.6 * len."""
        w_wide = self.service.state.get(self.service.add_text(0, 0, "WWWWWWWWWW", font_size=20)["text_id"])["width"]
        w_narrow = self.service.state.get(self.service.add_text(0, 0, "iiiiiiiiii", font_size=20)["text_id"])["width"]
        self.assertGreater(w_wide, w_narrow)
        expected_w, _, _ = measure_text_dimensions("WWWWWWWWWW", font_family=2, font_size=20)
        self.assertAlmostEqual(w_wide, expected_w, places=1)

    def test_wrap_text_to_shape_wraps_narrow_containers(self):
        """Regression for BUG-011: narrow shapes must wrap below 20 chars using pixel width."""
        wrapped = wrap_text_to_shape("ABCDEFGHIJKLMNOPQRST", shape="rectangle", target_w=100, font_size=20)
        self.assertIn("\n", wrapped)
        for line in wrapped.splitlines():
            lw, _, _ = measure_text_dimensions(line, font_size=20)
            self.assertLessEqual(lw, 70.0)

    def test_required_container_size_diamond_satisfies_rhombus_inequality(self):
        """Regression for BUG-012: diamond required_container_size must satisfy tw/W + th/H <= 1.0."""
        from excalidraw_mcp.text_padding import required_container_size

        for tw, th in ((400.0, 120.0), (200.0, 200.0), (80.0, 30.0)):
            w, h = required_container_size("diamond", tw, th)
            self.assertLess((tw / w) + (th / h), 1.0)


if __name__ == "__main__":
    unittest.main()
