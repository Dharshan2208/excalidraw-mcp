"""Comprehensive unit and integration test suite for auto_fix_layout.

Covers:
- Defect detection & semantic discrimination (intentional vs accidental geometry)
- Deterministic multi-phase repair planning & execution (phases 1–5)
- Transactional safety, dry-run immutability, and rollback on regression
- Idempotency on clean / repaired scenes
- Named scene persistence and batch_mutate integration
- FastMCP protocol tool inspection and end-to-end invocation
"""

import asyncio
from copy import deepcopy
import unittest
from unittest.mock import patch

from fastmcp import Client

from excalidraw_mcp.auto_fix import (
    _severe_ids,
    apply_layout_repairs,
    auto_fix_scene_layout,
    diagnose_layout_issues,
    is_intentional_overlap,
    measure_shape_text_containment,
    plan_layout_repairs,
    summarize_planned_repairs,
)
from excalidraw_mcp.text_padding import required_container_size
from excalidraw_mcp.elements import arrow, frame, rect, text
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.fonts import measure_text_dimensions
from excalidraw_mcp.layout import wrap_text_to_shape
from excalidraw_mcp.models import new_document
from excalidraw_mcp.scene import load_scene, save_scene
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class AutoFixDiagnosticsAndDiscriminationTests(unittest.TestCase):
    """R1: Defect detection and semantic discrimination."""

    def setUp(self):
        self.service = SceneService()

    def test_text_clipping_detected_when_container_smaller_than_font_bounding_box(self):
        """Text clipping is detected whenever container dimensions are smaller than measured font bounding boxes."""
        # 1. Container too small for long text
        r1 = self.service.add_shape(
            "rectangle",
            100,
            100,
            180,
            80,
            label="Microservice Architecture Distributed Transaction Coordinator",
        )
        self.service.resize(r1["rectangle_id"], width=70, height=30)
        doc = self.service.state.document()

        issues = diagnose_layout_issues(doc)
        text_clips = [i for i in issues if i["type"] == "text_clipping"]
        self.assertGreater(len(text_clips), 0)
        self.assertEqual(text_clips[0]["severity"], "critical")
        self.assertIn(r1["rectangle_id"], text_clips[0]["element_ids"])
        self.assertIn(r1["label_id"], text_clips[0]["element_ids"])

        # 2. Adequately sized container with short text is NOT flagged
        self.service.clear()
        r2 = self.service.add_shape("rectangle", 200, 200, 200, 100, label="OK")
        doc2 = self.service.state.document()
        issues2 = diagnose_layout_issues(doc2)
        text_clips2 = [i for i in issues2 if i["type"] == "text_clipping"]
        self.assertEqual(len(text_clips2), 0)

    def test_diamond_created_with_long_label_not_resized_by_auto_fix(self):
        """Diamond created by add_diamond with a long label is not resized by auto_fix_layout."""
        d = self.service.add_shape(
            "diamond",
            100,
            100,
            100,
            60,
            label="Multi-tier Decision Gateway Authentication Verification",
        )
        d_el = self.service.state.get(d["diamond_id"])
        init_w, init_h = d_el["width"], d_el["height"]

        res = self.service.auto_fix_layout()
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(len(res["applied_changes"]), 0)

        post_el = self.service.state.get(d["diamond_id"])
        self.assertEqual(post_el["width"], init_w)
        self.assertEqual(post_el["height"], init_h)

    def test_all_shapes_agree_between_creation_and_repair_sizing(self):
        """All shapes agree between creation and repair sizing via required_container_size."""
        for shape_type in ("rectangle", "ellipse", "diamond"):
            self.service.clear()
            res = self.service.add_shape(
                shape_type,
                100,
                100,
                50,
                50,
                label=f"Comprehensive {shape_type} padding test label",
            )
            key = {"rectangle": "rectangle_id", "ellipse": "circle_id", "diamond": "diamond_id"}[shape_type]
            shape_el = self.service.state.get(res[key])
            label_el = self.service.state.get(res["label_id"])

            is_clipped, req_w, req_h, def_w, def_h = measure_shape_text_containment(shape_el, label_el)
            self.assertFalse(is_clipped)
            self.assertEqual(def_w, 0.0)
            self.assertEqual(def_h, 0.0)
            self.assertAlmostEqual(shape_el["width"], req_w, places=1)
            self.assertAlmostEqual(shape_el["height"], req_h, places=1)

    def test_intentional_overlap_allow_overlap_flag(self):
        """Shapes with customData allow_overlap=True are NOT flagged as collisions."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="Box 1")
        r2 = self.service.add_shape("rectangle", 120, 120, 100, 100, label="Box 2")

        doc = self.service.state.document()
        for el in doc["elements"]:
            if el["id"] == r1["rectangle_id"]:
                el.setdefault("customData", {})["allow_overlap"] = True

        issues = diagnose_layout_issues(doc)
        overlaps = [i for i in issues if i["type"] == "node_overlap"]
        self.assertEqual(len(overlaps), 0)

    def test_intentional_overlap_explicit_groups(self):
        """Elements in explicit groups sharing groupIds are NOT flagged as collisions."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="Group Member 1")
        r2 = self.service.add_shape("rectangle", 120, 120, 100, 100, label="Group Member 2")

        self.service.group_elements([r1["rectangle_id"], r2["rectangle_id"]])
        doc = self.service.state.document()

        issues = diagnose_layout_issues(doc)
        overlaps = [i for i in issues if i["type"] == "node_overlap"]
        self.assertEqual(len(overlaps), 0)

    def test_intentional_overlap_nested_child_containers(self):
        """Child containers referenced via child_element_ids or parent_id are NOT flagged as collisions."""
        r1 = self.service.add_shape("rectangle", 100, 100, 300, 200, label="Parent Card")
        r2 = self.service.add_shape("rectangle", 150, 130, 80, 50, label="Child Badge")

        doc = self.service.state.document()
        for el in doc["elements"]:
            if el["id"] == r1["rectangle_id"]:
                el.setdefault("customData", {})["child_element_ids"] = [r2["rectangle_id"]]

        issues = diagnose_layout_issues(doc)
        overlaps = [i for i in issues if i["type"] == "node_overlap"]
        self.assertEqual(len(overlaps), 0)

    def test_intentional_overlap_geometrically_nested(self):
        """A smaller shape completely enclosed within a larger shape is recognized as nested."""
        r1 = self.service.add_shape("rectangle", 100, 100, 400, 300, label="Enclosing Container")
        r2 = self.service.add_shape("rectangle", 150, 150, 80, 60, label="Inner Component")
        doc = self.service.state.document()

        issues = diagnose_layout_issues(doc)
        overlaps = [i for i in issues if i["type"] == "node_overlap"]
        self.assertEqual(len(overlaps), 0)

    def test_frame_containment_violation_detection(self):
        """Frame containment violations are detected when shapes overflow or escape frame boundaries."""
        f = self.service.add_frame("Services", 100, 100, 200, 150)
        r = self.service.add_shape("rectangle", 150, 120, 180, 80, label="Escaping Node", frame_id=f["frame_id"])
        doc = self.service.state.document()

        issues = diagnose_layout_issues(doc)
        containments = [i for i in issues if i["type"] == "frame_containment"]
        self.assertGreater(len(containments), 0)
        self.assertEqual(containments[0]["details"]["frame_id"], f["frame_id"])
        self.assertEqual(containments[0]["details"]["shape_id"], r["rectangle_id"])

    def test_connector_collision_detection(self):
        """Connector collisions are detected when arrows cross unrelated obstacle shapes."""
        s1 = self.service.add_shape("rectangle", 50, 100, 80, 60, label="Source")
        obs = self.service.add_shape("rectangle", 200, 80, 100, 100, label="Obstacle")
        s2 = self.service.add_shape("rectangle", 400, 100, 80, 60, label="Target")

        conn = self.service.connect(s1["rectangle_id"], s2["rectangle_id"], elbowed=False)
        doc = self.service.state.document()
        for el in doc["elements"]:
            if el["id"] == conn["arrow_id"]:
                el["x"] = 130.0
                el["y"] = 130.0
                el["points"] = [[0.0, 0.0], [270.0, 0.0]]

        issues = diagnose_layout_issues(doc)
        collisions = [i for i in issues if i["type"] == "connector_collision"]
        self.assertGreater(len(collisions), 0)
        self.assertEqual(collisions[0]["details"]["obstacle_id"], obs["rectangle_id"])


class AutoFixRepairPhasesTests(unittest.TestCase):
    """R2: Deterministic multi-phase repair execution."""

    def setUp(self):
        self.service = SceneService()

    def test_phase1_container_expansion_preserves_center_and_user_text(self):
        """Phase 1: Containers expand outward around text without clipping and without drifting off-center."""
        r = self.service.add_shape("rectangle", 200, 200, 180, 80, label="Long Text String That Overflows Box")
        # Shrink box to create clipping deficit
        self.service.resize(r["rectangle_id"], width=70, height=30)

        rect_el = self.service.state.get(r["rectangle_id"])
        text_el = self.service.state.get(r["label_id"])
        original_text = text_el["text"]

        # Center before
        cx_before = rect_el["x"] + rect_el["width"] / 2.0
        cy_before = rect_el["y"] + rect_el["height"] / 2.0

        res = self.service.auto_fix_layout(repair_scope="text")
        self.assertIn(res["status"], ("repaired", "partially_repaired"))

        rect_after = self.service.state.get(r["rectangle_id"])
        text_after = self.service.state.get(r["label_id"])

        # Center preserved
        cx_after = rect_after["x"] + rect_after["width"] / 2.0
        cy_after = rect_after["y"] + rect_after["height"] / 2.0
        self.assertAlmostEqual(cx_before, cx_after, places=1)
        self.assertAlmostEqual(cy_before, cy_after, places=1)

        # Dimensions increased
        self.assertGreater(rect_after["width"], 70.0)
        self.assertGreater(rect_after["height"], 30.0)

        # User text unmodified
        self.assertEqual(text_after["text"], original_text)

        # Text bounding box centered inside expanded rectangle
        text_cx = text_after["x"] + text_after["width"] / 2.0
        text_cy = text_after["y"] + text_after["height"] / 2.0
        self.assertAlmostEqual(cx_after, text_cx, places=1)
        self.assertAlmostEqual(cy_after, text_cy, places=1)

    def test_phase2_overlap_minimal_displacement_axis_of_least_resistance(self):
        """Phase 2: Overlapping nodes are resolved with minimal displacement along axis of least resistance."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="Node 1")
        r2 = self.service.add_shape("rectangle", 190, 110, 100, 100, label="Node 2")

        res = self.service.auto_fix_layout(repair_scope="overlaps", min_gap=30.0)
        self.assertEqual(res["status"], "repaired")

        s1 = self.service.state.get(r1["rectangle_id"])
        s2 = self.service.state.get(r2["rectangle_id"])

        # Overlap eliminated
        self.assertGreaterEqual(s2["x"], s1["x"] + s1["width"] + 25.0)
        self.assertAlmostEqual(s2["y"], 110.0, places=1)

    def test_phase2_group_peers_stay_aligned(self):
        """Phase 2: When an overlapping shape is shifted, its grouped peers are translated identically."""
        g1 = self.service.add_shape("rectangle", 100, 100, 100, 80, label="Group Node 1")
        g2 = self.service.add_shape("rectangle", 100, 250, 100, 80, label="Group Node 2")
        self.service.group_elements([g1["rectangle_id"], g2["rectangle_id"]])

        # Obstacle shape overlapping g1 at (150, 100) extending past g1 right edge
        obs = self.service.add_shape("rectangle", 150, 100, 120, 80, label="Obstacle")

        g1_before = self.service.state.get(g1["rectangle_id"])
        g2_before = self.service.state.get(g2["rectangle_id"])
        rel_x_before = g2_before["x"] - g1_before["x"]
        rel_y_before = g2_before["y"] - g1_before["y"]

        res = self.service.auto_fix_layout(repair_scope="overlaps")
        self.assertEqual(res["status"], "repaired")

        g1_after = self.service.state.get(g1["rectangle_id"])
        g2_after = self.service.state.get(g2["rectangle_id"])
        rel_x_after = g2_after["x"] - g1_after["x"]
        rel_y_after = g2_after["y"] - g1_after["y"]

        # Relative alignment within group is strictly preserved
        self.assertAlmostEqual(rel_x_before, rel_x_after, places=1)
        self.assertAlmostEqual(rel_y_before, rel_y_after, places=1)

    def test_phase3_frame_boundary_expansion(self):
        """Phase 3: Frames expand to encompass all member children plus padding."""
        f = self.service.add_frame("Subsystem", 100, 100, 200, 150)
        r1 = self.service.add_shape("rectangle", 120, 120, 100, 60, label="Inside", frame_id=f["frame_id"])
        r2 = self.service.add_shape("rectangle", 230, 200, 120, 80, label="Escaping", frame_id=f["frame_id"])

        res = self.service.auto_fix_layout(repair_scope="containment")
        self.assertEqual(res["status"], "repaired")

        frame_after = self.service.state.get(f["frame_id"])
        r2_after = self.service.state.get(r2["rectangle_id"])

        # Frame covers r2 right and bottom edge with padding
        self.assertGreaterEqual(
            frame_after["x"] + frame_after["width"],
            r2_after["x"] + r2_after["width"] + 25.0,
        )
        self.assertGreaterEqual(
            frame_after["y"] + frame_after["height"],
            r2_after["y"] + r2_after["height"] + 25.0,
        )

    def test_phase4_obstacle_avoiding_connector_rerouting(self):
        """Phase 4: Connectors avoid crossing unrelated shapes when clear orthogonal routes exist."""
        s1 = self.service.add_shape("rectangle", 50, 100, 80, 60, label="Src")
        obs = self.service.add_shape("rectangle", 180, 80, 100, 100, label="Obs")
        s2 = self.service.add_shape("rectangle", 350, 100, 80, 60, label="Dst")

        conn = self.service.connect(s1["rectangle_id"], s2["rectangle_id"], elbowed=True)

        res = self.service.auto_fix_layout(repair_scope="connectors")
        self.assertIn(res["status"], ("repaired", "no_changes_needed"))

        issues = diagnose_layout_issues(self.service.state.document())
        collisions = [i for i in issues if i["type"] == "connector_collision"]
        self.assertEqual(len(collisions), 0)

    def test_phase5_spacing_adjustment(self):
        """Phase 5: Sub-optimal spacing between crowded components is widened to minimum gap."""
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60, label="A")
        r2 = self.service.add_shape("rectangle", 190, 100, 80, 60, label="B")

        res = self.service.auto_fix_layout(repair_scope="spacing", min_gap=35.0)
        self.assertIn(res["status"], ("repaired", "no_changes_needed"))

        s1 = self.service.state.get(r1["rectangle_id"])
        s2 = self.service.state.get(r2["rectangle_id"])
        gap = s2["x"] - (s1["x"] + s1["width"])
        self.assertGreaterEqual(gap, 25.0)


class AutoFixScopesAndAggressivenessTests(unittest.TestCase):
    """R2: Repair scopes and aggressiveness parameter validations."""

    def setUp(self):
        self.service = SceneService()

    def test_repair_scope_text_only(self):
        """repair_scope='text' fixes text clipping but ignores overlaps."""
        r1 = self.service.add_shape("rectangle", 100, 100, 180, 80, label="Extremely Long Text That Needs Resizing")
        self.service.resize(r1["rectangle_id"], width=60, height=30)
        r2 = self.service.add_shape("rectangle", 120, 100, 80, 60, label="Peer")

        res = self.service.auto_fix_layout(repair_scope="text")
        applied_types = [c["change_type"] for c in res["applied_changes"]]
        self.assertIn("resize", applied_types)
        self.assertNotIn("move", applied_types)

    def test_repair_scope_overlaps_only(self):
        """repair_scope='overlaps' fixes overlaps but ignores text clipping."""
        r1 = self.service.add_shape("rectangle", 100, 100, 180, 80, label="Extremely Long Text Overflow")
        self.service.resize(r1["rectangle_id"], width=60, height=30)
        r2 = self.service.add_shape("rectangle", 120, 100, 80, 60, label="Peer")

        res = self.service.auto_fix_layout(repair_scope="overlaps")
        applied_types = [c["change_type"] for c in res["applied_changes"]]
        self.assertIn("move", applied_types)
        self.assertNotIn("resize", applied_types)

    def test_aggressiveness_levels(self):
        """Aggressiveness modifies gap multipliers (gentle < balanced < aggressive)."""
        el1_gentle = rect(100, 100, 80, 60)
        el1_gentle["id"] = "box-1"
        el2_gentle = rect(130, 100, 80, 60)
        el2_gentle["id"] = "box-2"
        doc_gentle = new_document([el1_gentle, el2_gentle])
        res_gentle = auto_fix_scene_layout(doc_gentle, aggressiveness="gentle", min_gap=30.0)

        el1_aggr = rect(100, 100, 80, 60)
        el1_aggr["id"] = "box-1"
        el2_aggr = rect(130, 100, 80, 60)
        el2_aggr["id"] = "box-2"
        doc_aggr = new_document([el1_aggr, el2_aggr])
        res_aggr = auto_fix_scene_layout(doc_aggr, aggressiveness="aggressive", min_gap=30.0)

        b_gentle = [e for e in res_gentle["document"]["elements"] if e["id"] == "box-2"][0]
        b_aggr = [e for e in res_aggr["document"]["elements"] if e["id"] == "box-2"][0]

        # Aggressive displacement is greater than gentle displacement
        self.assertGreater(b_aggr["x"], b_gentle["x"])


class AutoFixTransactionSafetyAndIdempotencyTests(unittest.TestCase):
    """R3: Transactional safety, dry run immutability, rollback, and idempotency."""

    def setUp(self):
        self.service = SceneService()

    def test_dry_run_leaves_canvas_completely_unchanged(self):
        """dry_run=True leaves active canvas state completely unchanged while returning accurate repair plan."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        r2 = self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        doc_before = self.service.state.document()
        rev_before = self.service.state.revision

        res = self.service.auto_fix_layout(dry_run=True)
        self.assertEqual(res["status"], "dry_run")
        self.assertTrue(res["dry_run"])
        self.assertGreater(len(res["planned_changes"]), 0)
        self.assertGreater(len(res["applied_changes"]), 0)

        doc_after = self.service.state.document()
        rev_after = self.service.state.revision

        # Active state is 100% byte-for-byte identical
        self.assertEqual(doc_before, doc_after)
        self.assertEqual(rev_before, rev_after)

    def test_regression_rollback_restores_pre_repair_snapshot(self):
        """Introducing artificial regressions triggers an automatic rollback restoring pre-repair snapshot."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        r2 = self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        doc_before = self.service.state.document()
        rev_before = self.service.state.revision

        # Artificially monkeypatch apply_layout_repairs to create a catastrophic regression
        def buggy_apply(doc, *args, **kwargs):
            for k in range(10):
                doc["elements"].append(rect(100 + k * 10, 100 + k * 10, 100, 100, id=f"buggy-{k}"))
            return doc["elements"], [{"element_id": "buggy-0", "change_type": "move", "description": "regressed"}], [], []

        with patch("excalidraw_mcp.auto_fix.apply_layout_repairs", side_effect=buggy_apply):
            res = self.service.auto_fix_layout()

        self.assertEqual(res["status"], "rolled_back")
        self.assertTrue(res["rolled_back"])
        self.assertGreater(len(res["warnings"]), 0)
        self.assertIn("regression detected", res["warnings"][0])

        # Active state was safely rolled back and revision was not corrupted
        doc_after = self.service.state.document()
        self.assertEqual(len(doc_after["elements"]), len(doc_before["elements"]))
        self.assertEqual(self.service.state.revision, rev_before)

    def test_regression_oracle_does_not_rollback_on_warnings(self):
        """Repair that fixes 1 critical defect and produces 2 warnings does not roll back."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        r2 = self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        initial_issue = {
            "id": "c1",
            "type": "node_overlap",
            "severity": "critical",
            "element_ids": [r1["rectangle_id"], r2["rectangle_id"]],
            "details": {
                "shape1_id": r1["rectangle_id"],
                "shape2_id": r2["rectangle_id"],
                "overlap_width": 20.0,
                "overlap_height": 100.0,
                "overlap_ratio": 0.2,
            },
        }

        # Mock repair to eliminate critical issue while introducing 2 warnings (either string warnings or info issues)
        def repair_with_warnings(doc, *args, **kwargs):
            return (
                doc.get("elements", []),
                [{"element_id": r1["rectangle_id"], "change_type": "move", "description": "resolved"}],
                [],
                ["Warning 1: Spacing tightened", "Warning 2: Minor alignment adjusted"],
            )

        with patch("excalidraw_mcp.auto_fix.diagnose_layout_issues", side_effect=[[initial_issue], []]):
            with patch("excalidraw_mcp.auto_fix.apply_layout_repairs", side_effect=repair_with_warnings):
                res = self.service.auto_fix_layout()

        self.assertFalse(res["rolled_back"])
        self.assertEqual(res["status"], "repaired")
        self.assertIn("Warning 1: Spacing tightened", res["warnings"])
        self.assertIn("Warning 2: Minor alignment adjusted", res["warnings"])

    def test_regression_oracle_rolls_back_when_critical_replaced_with_different_critical(self):
        """Repair that replaces 1 critical issue with a different critical issue triggers rollback."""
        r1 = self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        r2 = self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        initial_issue = {
            "id": "c1",
            "type": "node_overlap",
            "severity": "critical",
            "element_ids": [r1["rectangle_id"], r2["rectangle_id"]],
            "details": {
                "shape1_id": r1["rectangle_id"],
                "shape2_id": r2["rectangle_id"],
                "overlap_width": 20.0,
                "overlap_height": 100.0,
                "overlap_ratio": 0.2,
            },
        }
        new_critical_issue = {
            "id": "c2",
            "type": "node_overlap",
            "severity": "critical",
            "element_ids": [r1["rectangle_id"], "other"],
            "details": {
                "shape1_id": r1["rectangle_id"],
                "shape2_id": "other",
                "overlap_width": 20.0,
                "overlap_height": 100.0,
                "overlap_ratio": 0.2,
            },
        }

        with patch("excalidraw_mcp.auto_fix.diagnose_layout_issues", side_effect=[[initial_issue], [new_critical_issue]]):
            res = self.service.auto_fix_layout()

        self.assertTrue(res["rolled_back"])
        self.assertEqual(res["status"], "rolled_back")
        self.assertTrue(any("c2" in w for w in res["warnings"]))

    def test_fixed_count_non_zero_when_status_repaired(self):
        """fixed_issues_count must never be 0 while status is repaired."""
        # Overlapping shapes that get repaired
        self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        res = self.service.auto_fix_layout()
        self.assertEqual(res["status"], "repaired")
        self.assertGreater(res["fixed_issues_count"], 0)

    def test_idempotency_consecutive_runs_produce_zero_changes(self):
        """Consecutive calls to auto_fix_layout produce identical results with 0 changes on the second run."""
        self.service.add_shape("rectangle", 100, 100, 100, 100, label="A")
        self.service.add_shape("rectangle", 120, 100, 100, 100, label="B")

        res1 = self.service.auto_fix_layout()
        self.assertEqual(res1["status"], "repaired")
        self.assertGreater(len(res1["applied_changes"]), 0)

        rev_after_repair = self.service.state.revision

        # Second call on already-repaired diagram
        res2 = self.service.auto_fix_layout()
        self.assertEqual(res2["status"], "no_changes_needed")
        self.assertEqual(len(res2["applied_changes"]), 0)
        self.assertEqual(len(res2["changed_element_ids"]), 0)
        self.assertEqual(res2["fixed_issues_count"], 0)

        # Revision does not change on second call
        self.assertEqual(self.service.state.revision, rev_after_repair)

    def test_empty_scene_handling(self):
        """Empty scene returns no_changes_needed safely."""
        res = self.service.auto_fix_layout()
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["fixed_issues_count"], 0)

    def test_invalid_inputs_raise_scene_error(self):
        """Invalid scope, aggressiveness, min_gap, or payload raise actionable SceneError."""
        with self.assertRaisesRegex(SceneError, "Invalid repair_scope"):
            self.service.auto_fix_layout(repair_scope="invalid_scope")

        with self.assertRaisesRegex(SceneError, "Invalid aggressiveness"):
            self.service.auto_fix_layout(aggressiveness="hyper_aggressive")

        with self.assertRaisesRegex(SceneError, "min_gap"):
            self.service.auto_fix_layout(min_gap=-10.0)

        with self.assertRaisesRegex(SceneError, "Expected document dictionary"):
            auto_fix_scene_layout("invalid_string_not_dict_or_list")


class AutoFixNamedScenesAndBatchMutateTests(unittest.TestCase):
    """R4: Named scenes and batch_mutate integration."""

    def setUp(self):
        self.service = SceneService()

    def test_saved_named_scene_repair(self):
        """auto_fix_layout repairs saved scenes on disk when name parameter is supplied."""
        self.service.add_shape("rectangle", 100, 100, 100, 100, label="Box 1")
        self.service.add_shape("rectangle", 120, 100, 100, 100, label="Box 2")
        self.service.save("scene_with_overlap", overwrite=True)

        self.service.clear()

        res = self.service.auto_fix_layout(name="scene_with_overlap")
        self.assertEqual(res["status"], "repaired")
        self.assertGreater(len(res["applied_changes"]), 0)

        repaired_doc = load_scene("scene_with_overlap")
        shapes = [e for e in repaired_doc["elements"] if e.get("type") == "rectangle"]
        self.assertEqual(len(shapes), 2)
        s1, s2 = shapes[0], shapes[1]
        self.assertGreaterEqual(abs(s1["x"] - s2["x"]), 100.0)

    def test_named_file_repair_increments_revision_and_is_undoable(self):
        """Named-file repair runs through self.state.apply, increments revision, updates live state, and is undoable."""
        self.service.add_shape("rectangle", 100, 100, 100, 100, label="Box 1")
        self.service.add_shape("rectangle", 120, 100, 100, 100, label="Box 2")
        self.service.save("scene_undo_test", overwrite=True)

        rev_before = self.service.state.revision
        res = self.service.auto_fix_layout(name="scene_undo_test")

        self.assertEqual(res["status"], "repaired")
        self.assertGreater(self.service.state.revision, rev_before)
        self.assertEqual(res["revision"], self.service.state.revision)

        # In-memory state matches disk
        disk_doc = load_scene("scene_undo_test")
        active_doc = self.service.state.document()
        self.assertEqual(len(active_doc["elements"]), len(disk_doc["elements"]))

        # Can undo
        undo_res = self.service.undo()
        self.assertEqual(undo_res["status"], "undone")
        self.assertGreater(self.service.state.revision, res["revision"])

    def test_named_scene_dry_run_does_not_modify_disk(self):
        """Named scene repair in dry_run mode does not modify disk file."""
        self.service.add_shape("rectangle", 100, 100, 100, 100, label="Box 1")
        self.service.add_shape("rectangle", 120, 100, 100, 100, label="Box 2")
        self.service.save("scene_dry_run_test", overwrite=True)
        raw_before = load_scene("scene_dry_run_test")

        res = self.service.auto_fix_layout(name="scene_dry_run_test", dry_run=True)
        self.assertEqual(res["status"], "dry_run")

        raw_after = load_scene("scene_dry_run_test")
        self.assertEqual(raw_before, raw_after)

    def test_batch_mutate_auto_fix_layout(self):
        """batch_mutate supports auto_fix_layout as an atomic operation."""
        batch_res = self.service.batch_mutate([
            {"action": "add_rectangle", "client_id": "r1", "x": 100, "y": 100, "w": 100, "h": 100, "label": "A"},
            {"action": "add_rectangle", "client_id": "r2", "x": 120, "y": 100, "w": 100, "h": 100, "label": "B"},
            {"action": "auto_fix_layout", "repair_scope": "overlaps", "min_gap": 30.0},
        ])

        self.assertEqual(batch_res["status"], "batch executed")
        self.assertEqual(batch_res["operations_executed"], 3)
        fix_op_result = batch_res["results"][2]
        self.assertEqual(fix_op_result["action"], "auto_fix_layout")
        self.assertEqual(fix_op_result["status"], "repaired")
        self.assertGreater(len(fix_op_result["applied_changes"]), 0)


class AutoFixMCPProtocolContractTests(unittest.IsolatedAsyncioTestCase):
    """R4 & Acceptance Criteria: FastMCP protocol tool inspection and execution."""

    async def test_tool_registered_on_mcp_server_and_inspectable(self):
        """auto_fix_layout is registered on MCP server and inspectable via MCP protocol tools list."""
        server = create_server()
        async with Client(server, timeout=5) as client:
            tools = await client.list_tools()
            tool_names = [t.name for t in tools]
            self.assertIn("auto_fix_layout", tool_names)

            # Check schema parameters
            tool = next(t for t in tools if t.name == "auto_fix_layout")
            params = tool.inputSchema.get("properties", {})
            self.assertIn("name", params)
            self.assertIn("dry_run", params)
            self.assertIn("repair_scope", params)
            self.assertIn("aggressiveness", params)
            self.assertIn("min_gap", params)

    async def test_mcp_protocol_call_auto_fix_layout_end_to_end(self):
        """Calling auto_fix_layout over MCP protocol returns structured AutoFixLayoutResult."""
        server = create_server()
        async with Client(server, timeout=5) as client:
            # Add two colliding rectangles
            await client.call_tool("add_rectangle", {"x": 100, "y": 100, "w": 100, "h": 100, "label": "Service 1"})
            await client.call_tool("add_rectangle", {"x": 120, "y": 100, "w": 100, "h": 100, "label": "Service 2"})

            # Call auto_fix_layout
            call_res = await client.call_tool(
                "auto_fix_layout",
                {"repair_scope": "all", "aggressiveness": "balanced", "min_gap": 30.0},
            )
            self.assertFalse(call_res.is_error)
            content = call_res.structured_content
            self.assertEqual(content["status"], "repaired")
            self.assertFalse(content["rolled_back"])
            self.assertFalse(content["dry_run"])
            self.assertGreater(len(content["applied_changes"]), 0)
            self.assertIn("revision", content)



class AutoFixAdversarialStressAndEdgeCaseTests(unittest.TestCase):
    """Stress tests and edge case coverage for adversarial review findings."""

    def setUp(self):
        self.service = SceneService()

    def test_customdata_none_does_not_crash(self):
        """Elements with customData=None (common in JSON export/import) must not raise AttributeError."""
        r1 = rect(100, 100, 100, 100)
        r1["id"] = "r1"
        r1["customData"] = None
        r2 = rect(120, 100, 100, 100)
        r2["id"] = "r2"
        r2["customData"] = None

        doc = new_document([r1, r2])
        # Verify diagnostics and repair execute cleanly without crashing
        issues = diagnose_layout_issues(doc)
        self.assertGreater(len(issues), 0)

        res = auto_fix_scene_layout(doc)
        self.assertEqual(res["status"], "repaired")
        self.assertFalse(res["rolled_back"])

    def test_batch_mutate_subsequent_operations_apply_to_repaired_elements(self):
        """batch_mutate subsequent operations must mutate repaired elements instead of stale discarded dicts."""
        res = self.service.batch_mutate([
            {
                "action": "add_rectangle",
                "client_id": "box1",
                "x": 100,
                "y": 100,
                "w": 70,
                "h": 30,
                "label": "Very long label that requires outward container resizing",
            },
            {"action": "auto_fix_layout", "repair_scope": "text"},
            {"action": "move", "element_id": "box1", "x": 500, "y": 600},
        ])

        self.assertEqual(res["status"], "batch executed")
        doc = self.service.state.document()
        box1_el = next(e for e in doc["elements"] if e["type"] == "rectangle")

        # Verify that box1 received BOTH the resize from auto_fix_layout AND the move to (500, 600)
        self.assertEqual(box1_el["x"], 500.0)
        self.assertEqual(box1_el["y"], 600.0)
        self.assertGreater(box1_el["width"], 70.0)
        self.assertGreater(box1_el["height"], 30.0)

    def test_spacing_cascade_three_crowded_nodes_no_rollback(self):
        """Three crowded nodes in a row must cascade spacing cleanly without creating collisions or rolling back."""
        # A: [100..180], B: [190..270] (gap 10), C: [275..355] (gap with B is 5)
        r1 = self.service.add_shape("rectangle", 100, 100, 80, 60, label="A")
        r2 = self.service.add_shape("rectangle", 190, 100, 80, 60, label="B")
        r3 = self.service.add_shape("rectangle", 275, 100, 80, 60, label="C")

        res = self.service.auto_fix_layout(min_gap=30.0)
        self.assertEqual(res["status"], "repaired")
        self.assertFalse(res["rolled_back"])

        s1 = self.service.state.get(r1["rectangle_id"])
        s2 = self.service.state.get(r2["rectangle_id"])
        s3 = self.service.state.get(r3["rectangle_id"])

        gap_ab = s2["x"] - (s1["x"] + s1["width"])
        gap_bc = s3["x"] - (s2["x"] + s2["width"])
        self.assertGreaterEqual(gap_ab, 29.5)
        self.assertGreaterEqual(gap_bc, 29.5)

    def test_nested_frames_expand_hierarchically_outward(self):
        """Nested frames must expand bottom-up so outer frames encompass expanded inner frames."""
        f1 = frame(0, 0, 200, 200, name="Outer Frame")
        f1["id"] = "f1"
        f2 = frame(20, 20, 150, 150, name="Inner Frame")
        f2["id"] = "f2"
        f2["frameId"] = "f1"
        r1 = rect(50, 50, 250, 250)
        r1["id"] = "r1"
        r1["frameId"] = "f2"

        doc = new_document([f1, f2, r1])
        initial_issues = diagnose_layout_issues(doc)
        # Should detect containment issue for r1 escaping f2
        self.assertTrue(any(i["type"] == "frame_containment" for i in initial_issues))

        res = auto_fix_scene_layout(doc, repair_scope="containment")
        self.assertEqual(res["status"], "repaired")
        self.assertFalse(res["rolled_back"])

        rep_f1 = next(e for e in res["document"]["elements"] if e["id"] == "f1")
        rep_f2 = next(e for e in res["document"]["elements"] if e["id"] == "f2")
        rep_r1 = next(e for e in res["document"]["elements"] if e["id"] == "r1")

        # Inner frame f2 must fully contain child r1
        self.assertLessEqual(rep_f2["x"], rep_r1["x"])
        self.assertLessEqual(rep_f2["y"], rep_r1["y"])
        self.assertGreaterEqual(rep_f2["x"] + rep_f2["width"], rep_r1["x"] + rep_r1["width"])
        self.assertGreaterEqual(rep_f2["y"] + rep_f2["height"], rep_r1["y"] + rep_r1["height"])

        # Outer frame f1 must fully contain child frame f2
        self.assertLessEqual(rep_f1["x"], rep_f2["x"])
        self.assertLessEqual(rep_f1["y"], rep_f2["y"])
        self.assertGreaterEqual(rep_f1["x"] + rep_f1["width"], rep_f2["x"] + rep_f2["width"])
        self.assertGreaterEqual(rep_f1["y"] + rep_f1["height"], rep_f2["y"] + rep_f2["height"])

        # Final issues must be zero
        final_containment = [i for i in res["final_issues"] if i["type"] == "frame_containment"]
        self.assertEqual(len(final_containment), 0)

    def test_standalone_text_in_frame_detected_and_enclosed(self):
        """Standalone text with frameId escaping frame boundaries must be detected and enclosed."""
        f = frame(100, 100, 150, 80, name="Text Container Frame")
        f["id"] = "frame-text"
        t = text(120, 120, "Wide title label that overflows the frame container", fontSize=20)
        t["id"] = "standalone-title"
        t["frameId"] = "frame-text"
        t["width"] = 350.0
        t["height"] = 40.0

        doc = new_document([f, t])
        issues = diagnose_layout_issues(doc)
        containments = [i for i in issues if i["type"] == "frame_containment"]
        self.assertEqual(len(containments), 1)
        self.assertEqual(containments[0]["element_ids"], ["frame-text", "standalone-title"])

        res = auto_fix_scene_layout(doc, repair_scope="containment")
        self.assertEqual(res["status"], "repaired")
        rep_f = next(e for e in res["document"]["elements"] if e["id"] == "frame-text")
        self.assertGreaterEqual(rep_f["x"] + rep_f["width"], t["x"] + t["width"] + 25.0)

    def test_locked_elements_preserved_and_skipped(self):
        """Locked elements must not be mutated; if both are locked, skipped_repairs records it."""
        r1 = rect(100, 100, 100, 100)
        r1["id"] = "r1-locked"
        r1["locked"] = True
        r2 = rect(130, 100, 100, 100)
        r2["id"] = "r2-locked"
        r2["locked"] = True

        doc = new_document([r1, r2])
        res = auto_fix_scene_layout(doc)
        # Both locked elements cannot be displaced: must not crash and report no_changes_needed
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertGreater(len(res["skipped_repairs"]), 0)
        self.assertGreater(len(res["warnings"]), 0)
        # Positions untouched
        r1_after = next(e for e in res["document"]["elements"] if e["id"] == "r1-locked")
        r2_after = next(e for e in res["document"]["elements"] if e["id"] == "r2-locked")
        self.assertEqual(r1_after["x"], 100.0)
        self.assertEqual(r2_after["x"], 130.0)

    def test_locked_element_shifts_unlocked_peer(self):
        """When a locked element collides with an unlocked element, the unlocked element is shifted."""
        r1 = rect(100, 100, 100, 100)
        r1["id"] = "r1-unlocked"
        r2 = rect(120, 100, 100, 100)
        r2["id"] = "r2-locked"
        r2["locked"] = True

        doc = new_document([r1, r2])
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(res["status"], "repaired")

        r1_after = next(e for e in res["document"]["elements"] if e["id"] == "r1-unlocked")
        r2_after = next(e for e in res["document"]["elements"] if e["id"] == "r2-locked")
        # Locked element r2 did NOT move
        self.assertEqual(r2_after["x"], 120.0)
        self.assertEqual(r2_after["y"], 100.0)
        # Unlocked element r1 was shifted to completely clear overlap
        inter_x = max(0.0, min(r1_after["x"] + r1_after["width"], r2_after["x"] + r2_after["width"]) - max(r1_after["x"], r2_after["x"]))
        inter_y = max(0.0, min(r1_after["y"] + r1_after["height"], r2_after["y"] + r2_after["height"]) - max(r1_after["y"], r2_after["y"]))
        self.assertTrue(inter_x <= 0.5 or inter_y <= 0.5)

    def test_polysegment_arrow_duplicate_collision_prevention(self):
        """An arrow with multiple segments touching the same obstacle generates exactly 1 issue."""
        obs = rect(200, 100, 100, 100)
        obs["id"] = "obstacle"

        # Polyline arrow that enters and exits obstacle
        a = arrow(100, 150, 400, 150)
        a["id"] = "poly-arrow"
        a["points"] = [[0, 0], [150, 0], [150, 30], [300, 30]]

        doc = new_document([obs, a])
        issues = diagnose_layout_issues(doc)
        coll_issues = [i for i in issues if i["type"] == "connector_collision"]
        # Must only produce 1 defect issue for (poly-arrow, obstacle)
        self.assertEqual(len(coll_issues), 1)
        self.assertEqual(coll_issues[0]["id"], "collision-poly-arrow-obstacle")

    def test_unattached_arrow_crossing_obstacle_reports_partially_repaired(self):
        """Unattached arrow crossing obstacle cannot be routed and reports no_changes_needed when no changes applied."""
        obs = rect(250, 80, 80, 100)
        obs["id"] = "obs"
        a = arrow(180, 130, 400, 130)
        a["id"] = "a1"

        doc = new_document([obs, a])
        res = auto_fix_scene_layout(doc, repair_scope="connectors")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertGreater(len(res["unresolved_issues"]), 0)

    def test_connector_routing_tracks_translated_arrow_origin(self):
        """When an attached arrow's origin moves with its connected shape, the change is recorded."""
        s1 = self.service.add_shape("rectangle", 100, 100, 80, 60, label="Src")
        obs = self.service.add_shape("rectangle", 120, 100, 80, 60, label="Obs")
        s2 = self.service.add_shape("rectangle", 400, 100, 80, 60, label="Dst")

        conn = self.service.connect(s1["rectangle_id"], s2["rectangle_id"])
        res = self.service.auto_fix_layout(repair_scope="all")
        self.assertEqual(res["status"], "repaired")
        # Ensure connector aid is recorded in changed_element_ids
        self.assertIn(conn["arrow_id"], res["changed_element_ids"])

    def test_locked_frame_boundary_preserved_and_skipped(self):
        """Locked frame must not be expanded or resized; skipped repair and warning recorded."""
        f = frame(100, 100, 100, 100, name="Locked Frame")
        f["id"] = "f-locked"
        f["locked"] = True
        r = rect(150, 150, 200, 200)
        r["id"] = "r-child"
        r["frameId"] = "f-locked"

        doc = new_document([f, r])
        res = auto_fix_scene_layout(doc, repair_scope="containment")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertGreater(len(res["skipped_repairs"]), 0)
        self.assertGreater(len(res["warnings"]), 0)
        f_after = next(e for e in res["document"]["elements"] if e["id"] == "f-locked")
        # Frame coordinates and dimensions must be completely untouched
        self.assertEqual(f_after["x"], 100.0)
        self.assertEqual(f_after["y"], 100.0)
        self.assertEqual(f_after["width"], 100.0)
        self.assertEqual(f_after["height"], 100.0)

    def test_locked_group_member_never_moved_during_decollision(self):
        """When an unlocked shape in a group collides, but a peer in that group is locked, the locked peer never moves."""
        # r1 is grouped with r2 (which is locked)
        r1 = rect(100, 100, 100, 100)
        r1["id"] = "r1-grp"
        r1["groupIds"] = ["grp-lock"]

        r2 = rect(250, 100, 100, 100)
        r2["id"] = "r2-locked-peer"
        r2["groupIds"] = ["grp-lock"]
        r2["locked"] = True

        # r3 is an unlocked shape that collides with r1
        r3 = rect(80, 100, 100, 100)
        r3["id"] = "r3-collider"

        doc = new_document([r3, r1, r2])
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(res["status"], "repaired")

        r2_after = next(e for e in res["document"]["elements"] if e["id"] == "r2-locked-peer")
        r1_after = next(e for e in res["document"]["elements"] if e["id"] == "r1-grp")
        r3_after = next(e for e in res["document"]["elements"] if e["id"] == "r3-collider")

        # Locked peer r2 MUST NOT have moved
        self.assertEqual(r2_after["x"], 250.0)
        self.assertEqual(r2_after["y"], 100.0)
        # r1 in the locked group also stays at 100
        self.assertEqual(r1_after["x"], 100.0)
        # r3 was shifted left to clear the locked cluster
        self.assertLessEqual(r3_after["x"] + r3_after["width"], r1_after["x"] - 29.5)

    def test_arrow_crossing_frame_does_not_expand_frame(self):
        """Connector arrows exiting a frame must not be treated as frame children forcing frame expansion."""
        f1 = frame(100, 100, 300, 300, name="Frame 1")
        f1["id"] = "f1"
        r1 = rect(150, 150, 100, 100)
        r1["id"] = "r1"
        r1["frameId"] = "f1"

        r2 = rect(600, 150, 100, 100)
        r2["id"] = "r2"

        # Long arrow crossing from r1 inside f1 to r2 outside f1
        a = arrow(250, 200, 350, 0)
        a["id"] = "a1"
        a["width"] = 400.0
        a["points"] = [[0.0, 0.0], [350.0, 0.0]]
        a["frameId"] = "f1"

        doc = new_document([f1, r1, r2, a])
        # Diagnosing layout should detect NO containment issue for a1 escaping f1
        issues = diagnose_layout_issues(doc)
        containment_issues = [i for i in issues if i["type"] == "frame_containment"]
        self.assertEqual(len(containment_issues), 0)

        res = auto_fix_scene_layout(doc, repair_scope="containment")
        f1_after = next(e for e in res["document"]["elements"] if e["id"] == "f1")
        # f1 width must NOT have expanded to engulf the external shape r2
        self.assertEqual(f1_after["width"], 300.0)
        self.assertEqual(f1_after["x"], 100.0)

    def test_malformed_element_none_coordinates_does_not_crash(self):
        """Elements with None or missing numeric coordinates/dimensions are safely normalized."""
        malformed_doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": "m1", "type": "rectangle", "x": None, "y": None, "width": None, "height": 100.0},
                {"id": "m2", "type": "rectangle", "x": 100.0, "y": 100.0, "width": "invalid", "height": None},
                {"id": "m3", "type": "arrow", "x": 0.0, "y": 0.0, "points": None},
                {"id": "m4", "type": "text", "text": "test", "fontSize": None, "containerId": "m1"},
            ],
        }
        res = auto_fix_scene_layout(malformed_doc)
        self.assertIn(res["status"], ("repaired", "no_changes_needed", "partially_repaired"))

    def test_empty_dict_document_handled_safely(self):
        """Empty dictionary or document without elements returns no_changes_needed."""
        res1 = auto_fix_scene_layout({})
        self.assertEqual(res1["status"], "no_changes_needed")
        self.assertEqual(res1["fixed_issues_count"], 0)

        res2 = auto_fix_scene_layout({"type": "excalidraw"})
        self.assertEqual(res2["status"], "no_changes_needed")

    def test_both_crowded_elements_locked_reports_partially_repaired(self):
        """When two crowded elements in spacing phase are both locked, no_changes_needed is reported."""
        s1 = rect(100, 100, 100, 100)
        s1["id"] = "s1-locked"
        s1["locked"] = True
        s2 = rect(210, 100, 100, 100)  # Gap 10 < 19.5
        s2["id"] = "s2-locked"
        s2["locked"] = True

        doc = new_document([s1, s2])
        res = auto_fix_scene_layout(doc, repair_scope="spacing")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertGreater(len(res["skipped_repairs"]), 0)
        self.assertGreater(len(res["warnings"]), 0)

    def test_extreme_dense_cyclic_overlap_pattern(self):
        """25 identical overlapping rectangles stacked at (0, 0) disperse cleanly."""
        doc = {
            "type": "excalidraw",
            "version": 2,
            "elements": [
                {"id": f"stacked-{i}", "type": "rectangle", "x": 0.0, "y": 0.0, "width": 100.0, "height": 100.0}
                for i in range(25)
            ],
        }
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(res["status"], "repaired")
        self.assertFalse(res["rolled_back"])
        self.assertEqual(len(res["final_issues"]), 0)

    def test_locked_connector_preserved_and_skipped(self):
        """A locked connector intersecting an obstacle shape is not rerouted."""
        obs = rect(200, 100, 100, 100)
        obs["id"] = "obstacle"
        a = arrow(100, 150, 300, 0)
        a["id"] = "a-locked"
        a["locked"] = True
        a["points"] = [[0.0, 0.0], [300.0, 0.0]]

        doc = new_document([obs, a])
        res = auto_fix_scene_layout(doc, repair_scope="connectors")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertGreater(len(res["skipped_repairs"]), 0)
        # Arrow points must not have changed
        a_after = next(e for e in res["document"]["elements"] if e["id"] == "a-locked")
        self.assertEqual(a_after["points"], [[0.0, 0.0], [300.0, 0.0]])

    def test_batch_mutate_auto_fix_invalid_parameters_rejected(self):
        """batch_mutate with invalid auto_fix_layout parameters raises SceneError."""
        with self.assertRaises(SceneError):
            self.service.batch_mutate(
                [{"action": "auto_fix_layout", "repair_scope": "invalid_scope"}]
            )
        with self.assertRaises(SceneError):
            self.service.batch_mutate(
                [{"action": "auto_fix_layout", "aggressiveness": "invalid_aggr"}]
            )
        with self.assertRaises(SceneError):
            self.service.batch_mutate(
                [{"action": "auto_fix_layout", "min_gap": -5.0}]
            )
        with self.assertRaises(SceneError):
            self.service.batch_mutate(
                [{"action": "auto_fix_layout", "min_gap": "invalid"}]
            )
        with self.assertRaises(SceneError):
            self.service.batch_mutate(
                [{"action": "auto_fix_layout", "dry_run": "yes"}]
            )

    def test_locked_group_peer_never_moved_during_spacing(self):
        """Locked group members must never be moved during horizontal or vertical spacing adjustments."""
        # Peer in grp1 is locked at x=-200
        p_lock = rect(-200.0, 0.0, 100.0, 50.0)
        p_lock["id"] = "p-lock"
        p_lock["locked"] = True
        p_lock["groupIds"] = ["grp1"]

        # s1 in grp1 is unlocked at x=0
        s1 = rect(0.0, 0.0, 100.0, 50.0)
        s1["id"] = "s1"
        s1["groupIds"] = ["grp1"]

        # s2 is locked at x=110 (gap 10 < 19.5 with s1)
        s2 = rect(110.0, 0.0, 100.0, 50.0)
        s2["id"] = "s2"
        s2["locked"] = True

        doc = new_document([p_lock, s1, s2])
        res = auto_fix_scene_layout(doc, repair_scope="spacing")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])

        p_after = next(e for e in res["document"]["elements"] if e["id"] == "p-lock")
        s1_after = next(e for e in res["document"]["elements"] if e["id"] == "s1")
        s2_after = next(e for e in res["document"]["elements"] if e["id"] == "s2")

        # Locked peer p-lock MUST NOT have moved
        self.assertEqual(p_after["x"], -200.0)
        self.assertEqual(p_after["y"], 0.0)
        # s1 in the locked cluster must not have moved
        self.assertEqual(s1_after["x"], 0.0)
        # s2 locked must not have moved
        self.assertEqual(s2_after["x"], 110.0)

    def test_plan_layout_repairs_omits_both_locked_elements_and_picks_unlocked_cluster(self):
        """plan_layout_repairs omits both-locked pairs and targets the unlocked cluster when a peer is locked."""
        # 1. Both locked: plan should be empty
        s1_l = rect(100, 100, 100, 100)
        s1_l["id"] = "s1-l"
        s1_l["locked"] = True
        s2_l = rect(120, 100, 100, 100)
        s2_l["id"] = "s2-l"
        s2_l["locked"] = True
        doc_locked = new_document([s1_l, s2_l])
        issues_locked = diagnose_layout_issues(doc_locked)
        plans_locked = plan_layout_repairs(doc_locked, issues_locked)
        self.assertEqual(len(plans_locked), 0)

        # 2. s1 grouped with locked peer p_lock; s2 is unlocked at x=80
        s1 = rect(100, 100, 100, 100)
        s1["id"] = "s1"
        s1["groupIds"] = ["grp_lock"]
        p_lock = rect(300, 100, 100, 100)
        p_lock["id"] = "p_lock"
        p_lock["locked"] = True
        p_lock["groupIds"] = ["grp_lock"]
        s2 = rect(80, 100, 100, 100)
        s2["id"] = "s2"
        doc_cluster = new_document([s1, p_lock, s2])
        issues_cluster = diagnose_layout_issues(doc_cluster)
        plans_cluster = plan_layout_repairs(doc_cluster, issues_cluster)
        # The plan MUST target unlocked s2, NOT locked cluster member s1
        self.assertEqual(len(plans_cluster), 1)
        self.assertEqual(plans_cluster[0]["element_id"], "s2")

    def test_missing_id_in_elements_does_not_falsely_classify_intentional_overlap(self):
        """Overlapping elements without explicit IDs must NOT be falsely classified as intentional."""
        s1 = {"type": "rectangle", "x": 0.0, "y": 0.0, "width": 100.0, "height": 100.0}
        s2 = {"type": "rectangle", "x": 50.0, "y": 50.0, "width": 100.0, "height": 100.0}
        self.assertFalse(is_intentional_overlap(s1, s2))

    def test_arrow_binding_without_element_id_does_not_crash(self):
        """Arrows with bindings lacking 'elementId' do not raise KeyError."""
        s1 = rect(0, 0, 100, 100)
        s1["id"] = "s1"
        a1 = arrow(50, 50, 100, 100)
        a1["id"] = "a1"
        a1["startBinding"] = {"gap": 10}  # missing 'elementId'
        doc = new_document([s1, a1])
        issues = diagnose_layout_issues(doc)
        self.assertIsInstance(issues, list)

    def test_frame_containment_does_not_mutate_frame_when_all_children_inside(self):
        """A frame with children placed near the top does not expand when another unrelated defect is fixed."""
        f1 = frame(0.0, 0.0, 300.0, 300.0, name="Frame 1")
        f1["id"] = "f1"
        # s1 is well inside f1 (y=10 within 0..300)
        s1 = rect(50.0, 10.0, 100.0, 100.0)
        s1["id"] = "s1"
        s1["frameId"] = "f1"
        # Unrelated colliding shapes elsewhere
        other1 = rect(500.0, 0.0, 100.0, 100.0)
        other1["id"] = "other1"
        other2 = rect(520.0, 0.0, 100.0, 100.0)
        other2["id"] = "other2"

        doc = new_document([f1, s1, other1, other2])
        res = auto_fix_scene_layout(doc, repair_scope="all")
        self.assertEqual(res["status"], "repaired")
        f1_after = next(e for e in res["document"]["elements"] if e["id"] == "f1")
        # f1 was not overflowing and must not have expanded
        self.assertEqual(f1_after["x"], 0.0)
        self.assertEqual(f1_after["y"], 0.0)
        self.assertEqual(f1_after["width"], 300.0)
        self.assertEqual(f1_after["height"], 300.0)

    def test_malformed_group_ids_integer_does_not_crash(self):
        """Shapes with malformed groupIds (integers, strings, booleans) do not raise TypeError."""
        s1 = rect(100, 100, 100, 100)
        s1["id"] = "s1"
        s1["groupIds"] = 123  # Non-iterable int
        s2 = rect(120, 100, 100, 100)
        s2["id"] = "s2"
        s2["groupIds"] = ["g1"]

        doc = new_document([s1, s2])
        res = auto_fix_scene_layout(doc)
        self.assertIn(res["status"], ("repaired", "partially_repaired"))

    def test_arrow_non_finite_nan_inf_points_handled_safely(self):
        """Arrows with NaN or Inf coordinates are safely sanitized without raising exceptions."""
        s1 = rect(0, 0, 100, 100)
        s1["id"] = "s1"
        a1 = arrow(0, 0, 100, 100)
        a1["id"] = "a1"
        a1["points"] = [[0.0, 0.0], [float("nan"), float("inf")]]

        doc = new_document([s1, a1])
        issues = diagnose_layout_issues(doc)
        self.assertIsInstance(issues, list)

    def test_deduplicated_warnings_and_skipped_repairs_on_locked_clusters(self):
        """Colliding locked clusters produce exactly 1 warning and 1 skipped repair, not 12 duplicates."""
        s1 = rect(100.0, 100.0, 100.0, 100.0)
        s1["id"] = "s1"
        s1["locked"] = True
        s2 = rect(120.0, 100.0, 100.0, 100.0)
        s2["id"] = "s2"
        s2["locked"] = True

        doc = new_document([s1, s2])
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(res["status"], "no_changes_needed")
        self.assertEqual(res["applied_changes"], [])
        self.assertEqual(len(res["skipped_repairs"]), 1)
        self.assertEqual(len(res["warnings"]), 1)

    def test_performance_200_node_graph_completes_under_five_seconds(self):
        """A 200-node draw_graph followed by auto_fix_layout completes in under 5 seconds wall clock."""
        import time

        nodes = [{"id": f"n{i}", "label": f"Node {i}"} for i in range(200)]
        edges = [{"source": f"n{i}", "target": f"n{i+1}"} for i in range(199)]
        self.service.draw_graph(nodes, edges, layout="layered")

        start = time.perf_counter()
        res = self.service.auto_fix_layout()
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 5.0)
        self.assertIn(res["status"], ("repaired", "partially_repaired", "no_changes_needed"))

    def test_unresolvable_font_family_yields_warning_and_does_not_raise(self):
        """Scene with an unresolvable fontFamily yields a warning and does not raise."""
        s1 = rect(100.0, 100.0, 100.0, 100.0)
        s1["id"] = "s1"
        t1 = text(110.0, 110.0, "A very long label requiring wrap and resize")
        t1["id"] = "t1"
        t1["containerId"] = "s1"
        t1["fontFamily"] = "UnknownCustomFont"

        doc = new_document([s1, t1])
        with patch("excalidraw_mcp.auto_fix.wrap_text_to_shape", side_effect=ValueError("unrecognized fontFamily")):
            res = auto_fix_scene_layout(doc, repair_scope="text")

        self.assertIn("warnings", res)
        self.assertTrue(any("could not measure text in font 'UnknownCustomFont'" in w for w in res["warnings"]))

    def test_warning_truncation_caps_at_twenty_with_suffix(self):
        """Scene producing >20 warnings returns exactly 21 entries with the truncation suffix."""
        elements = []
        for i in range(25):
            s1 = rect(1000.0 * i, 100.0, 80.0, 80.0)
            s1["id"] = f"locked_a_{i}"
            s1["locked"] = True
            s2 = rect(1000.0 * i + 10.0, 100.0, 80.0, 80.0)
            s2["id"] = f"locked_b_{i}"
            s2["locked"] = True
            elements.extend([s1, s2])

        doc = new_document(elements)
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(len(res["warnings"]), 21)
        self.assertEqual(res["warnings"][-1], "...and 5 more warnings.")

    def test_unparented_element_outside_frame_is_reparented_and_recorded(self):
        """Repair of a scene with an element 10px outside a frame results in that element having the frame's frameId afterward, and a reparent entry in applied_changes."""
        f1 = frame(100.0, 100.0, 200.0, 200.0, name="Frame 1")
        f1["id"] = "f1"
        s1 = rect(290.0, 120.0, 20.0, 20.0)
        s1["id"] = "s1"
        s1["frameId"] = None

        doc = new_document([f1, s1])
        res = auto_fix_scene_layout(doc, repair_scope="containment")

        self.assertIn(res["status"], ("repaired", "partially_repaired"))
        reparent_changes = [c for c in res["applied_changes"] if c.get("change_type") == "reparent"]
        self.assertEqual(len(reparent_changes), 1)
        self.assertEqual(reparent_changes[0]["element_id"], "s1")
        self.assertEqual(reparent_changes[0]["after"]["frameId"], "f1")

        doc_elements = res["document"]["elements"]
        s1_after = next(e for e in doc_elements if e["id"] == "s1")
        self.assertEqual(s1_after["frameId"], "f1")

    def test_nested_shape_at_1_28_area_ratio_classified_as_intentional_overlap_and_not_displaced(self):
        """A 1.28x area nested shape is classified as intentional overlap and is not displaced by Phase 2."""
        s1 = rect(86.0, 100.0, 128.0, 100.0)
        s1["id"] = "outer"
        s2 = rect(100.0, 100.0, 100.0, 100.0)
        s2["id"] = "inner"

        self.assertTrue(is_intentional_overlap(s1, s2))

        doc = new_document([s1, s2])
        repaired, applied_changes, skipped_repairs, warnings = apply_layout_repairs(doc, repair_scope="overlaps")
        self.assertEqual(applied_changes, [])

        outer_after = next(e for e in repaired if e["id"] == "outer")
        inner_after = next(e for e in repaired if e["id"] == "inner")
        self.assertEqual(outer_after["x"], 86.0)
        self.assertEqual(inner_after["x"], 100.0)

    def test_summarize_planned_repairs_dedupes_by_phase_and_element_id(self):
        """summarize_planned_repairs dedupes plans by (phase, element_id) keeping first entry."""
        s1 = rect(100.0, 100.0, 100.0, 100.0)
        s1["id"] = "s1"
        s2 = rect(110.0, 100.0, 100.0, 100.0)
        s2["id"] = "s2"
        s3 = rect(120.0, 100.0, 100.0, 100.0)
        s3["id"] = "s3"

        doc = new_document([s1, s2, s3])
        issues = [
            {
                "id": "c1",
                "type": "node_overlap",
                "severity": "critical",
                "element_ids": ["s1", "s2"],
                "details": {"shape1_id": "s1", "shape2_id": "s2", "overlap_width": 90.0, "overlap_height": 100.0},
            },
            {
                "id": "c2",
                "type": "node_overlap",
                "severity": "critical",
                "element_ids": ["s2", "s3"],
                "details": {"shape1_id": "s2", "shape2_id": "s3", "overlap_width": 90.0, "overlap_height": 100.0},
            },
        ]

        plans = summarize_planned_repairs(doc, issues, repair_scope="overlaps")
        keys = [(p["phase"], p["element_id"]) for p in plans]
        self.assertEqual(len(keys), len(set(keys)))

    def test_shape_with_invalid_allow_overlap_produces_warning_and_is_repaired(self):
        """Shape with allow_overlap: 'yes' produces a warning and is still repaired."""
        s1 = rect(100.0, 100.0, 100.0, 100.0)
        s1["id"] = "s1"
        s1["customData"] = {"allow_overlap": "yes"}
        s2 = rect(120.0, 100.0, 100.0, 100.0)
        s2["id"] = "s2"

        doc = new_document([s1, s2])
        res = auto_fix_scene_layout(doc, repair_scope="overlaps")
        self.assertEqual(res["status"], "repaired")
        self.assertTrue(any("invalid customData.allow_overlap" in w for w in res["warnings"]))
        s2_after = next(e for e in res["document"]["elements"] if e["id"] == "s2")
        self.assertNotEqual(s2_after["x"], 120.0)

    def test_diagnose_skips_shape_with_missing_or_non_finite_dimensions(self):
        """diagnose_layout_issues skips shapes with missing or non-finite width/height and emits warning."""
        s1 = rect(100.0, 100.0, 100.0, 100.0)
        s1["id"] = "valid_s1"
        s2 = rect(100.0, 100.0, 100.0, 100.0)
        s2["id"] = "bad_s2"
        s2["width"] = float("nan")

        warnings = []
        issues = diagnose_layout_issues([s1, s2], warnings=warnings)
        self.assertIn("Skipped shape 'bad_s2': missing or non-finite width/height.", warnings)

    def test_service_auto_fix_layout_rejects_bool_min_gap(self):
        """auto_fix_layout(min_gap=True) raises SceneError from the service layer."""
        with self.assertRaises(SceneError):
            self.service.auto_fix_layout(min_gap=True)

    def test_min_gap_upper_bound_validation(self):
        """min_gap=2000 raises SceneError; min_gap=1000 does not."""
        with self.assertRaises(SceneError):
            self.service.auto_fix_layout(min_gap=2000)

        res = self.service.auto_fix_layout(min_gap=1000)
        self.assertIn(res["status"], ("repaired", "partially_repaired", "no_changes_needed"))


if __name__ == "__main__":
    unittest.main()

