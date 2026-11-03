"""Automated layout repair engine for Excalidraw scenes.

Performs deterministic multi-phase defect detection, repair planning, transaction execution,
and before/after regression validation.
"""

from copy import deepcopy
import math
from typing import Any

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.fonts import measure_text_dimensions
from excalidraw_mcp.layout import wrap_text_to_shape
from excalidraw_mcp.routing import reroute_scene_arrows, segment_intersects_rect
from excalidraw_mcp.text_padding import required_container_size

VALID_SCOPES = ("all", "overlaps", "connectors", "containment", "text", "spacing")
VALID_AGGRESSIVENESS = ("gentle", "balanced", "aggressive")

TEXT_DEFICIT_THRESHOLD_PX = 1.0   # used by BOTH diagnose and repair
SPACING_RATIO_THRESHOLD = 0.65    # used by BOTH diagnose and repair
AGGRESSIVENESS_MULT = {"gentle": 0.8, "balanced": 1.0, "aggressive": 1.35}


def _validate_params(repair_scope: str, aggressiveness: str, min_gap: float) -> tuple[str, str, float]:
    """Validate repair parameters and return canonical forms."""
    if not isinstance(repair_scope, str) or repair_scope.lower() not in VALID_SCOPES:
        raise SceneError(
            f"Invalid repair_scope '{repair_scope}'. Must be one of: {', '.join(VALID_SCOPES)}"
        )
    if not isinstance(aggressiveness, str) or aggressiveness.lower() not in VALID_AGGRESSIVENESS:
        raise SceneError(
            f"Invalid aggressiveness '{aggressiveness}'. Must be one of: {', '.join(VALID_AGGRESSIVENESS)}"
        )
    if (
        isinstance(min_gap, bool)
        or not isinstance(min_gap, (int, float))
        or math.isnan(min_gap)
        or math.isinf(min_gap)
        or min_gap < 0
        or min_gap > 1000.0
    ):
        raise SceneError("min_gap must be between 0 and 1000")
    return repair_scope.lower(), aggressiveness.lower(), float(min_gap)


def _coord(el: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    """Safely extract finite float coordinate or dimension from an element."""
    if not isinstance(el, dict):
        return default
    v = el.get(key)
    if v is None:
        return default
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except (ValueError, TypeError):
        return default


def _extract_active_elements(document_or_elements: Any) -> tuple[list[dict[str, Any]], bool]:
    """Extract and validate active (non-deleted) elements from document dict or element list."""
    if isinstance(document_or_elements, dict):
        elements = document_or_elements.get("elements", [])
        is_doc = True
    elif isinstance(document_or_elements, list):
        elements = document_or_elements
        is_doc = False
    else:
        raise SceneError("Expected document dictionary or list of elements")

    if not isinstance(elements, list):
        raise SceneError("Document elements must be a list")

    active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
    return active, is_doc


def _severe_ids(issues: list[dict[str, Any]]) -> set[str]:
    """Extract IDs of critical and warning severity layout defects."""
    return {i["id"] for i in issues if i.get("severity") in ("critical", "warning")}


def _cd(el: dict[str, Any] | None) -> dict[str, Any]:
    """Safely extract customData dict from element, handling None or non-dict values."""
    if not isinstance(el, dict):
        return {}
    cd = el.get("customData")
    return cd if isinstance(cd, dict) else {}


def _get_group_ids(el: dict[str, Any] | None) -> set[str]:
    """Safely extract valid non-empty string group IDs from an element."""
    if not isinstance(el, dict):
        return set()
    raw = el.get("groupIds")
    if isinstance(raw, (list, tuple, set)):
        return {g for g in raw if isinstance(g, str) and g}
    return set()


def _build_group_index(shapes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Build a mapping from group ID to list of shapes possessing that group ID."""
    index: dict[str, list[dict[str, Any]]] = {}
    for s in shapes:
        for gid in _get_group_ids(s):
            index.setdefault(gid, []).append(s)
    return index


def _get_shape_cluster(
    target: dict[str, Any],
    group_index_or_shapes: dict[str, list[dict[str, Any]]] | list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Get all shapes transitively connected to target via shared groupIds using group_index."""
    target_groups = _get_group_ids(target)
    if not target_groups:
        return [target]

    if isinstance(group_index_or_shapes, list):
        group_index = _build_group_index(group_index_or_shapes)
    else:
        group_index = group_index_or_shapes

    cluster_shapes: dict[str, dict[str, Any]] = {}
    tid = target.get("id")
    if tid:
        cluster_shapes[tid] = target

    visited_groups = set()
    queue = list(target_groups)
    while queue:
        gid = queue.pop()
        if gid in visited_groups:
            continue
        visited_groups.add(gid)
        for s in group_index.get(gid, []):
            sid = s.get("id")
            if sid and sid not in cluster_shapes:
                cluster_shapes[sid] = s
                for next_gid in _get_group_ids(s):
                    if next_gid not in visited_groups:
                        queue.append(next_gid)

    return list(cluster_shapes.values()) if cluster_shapes else [target]


def _is_cluster_locked(cluster: list[dict[str, Any]]) -> bool:
    """Return True if any element in the cluster is locked."""
    return any(bool(s.get("locked")) for s in cluster)


def is_intentional_overlap(
    s1: dict[str, Any],
    s2: dict[str, Any],
    warnings: list[str] | None = None,
) -> bool:
    """Determine if overlap between two shapes is intentional."""
    ao1 = _cd(s1).get("allow_overlap")
    if ao1 is not None and not isinstance(ao1, bool):
        sid1 = s1.get("id", "unknown")
        msg = f"Shape '{sid1}' has invalid customData.allow_overlap (expected bool, got {type(ao1).__name__}); treating as false."
        if warnings is not None and msg not in warnings:
            warnings.append(msg)
        ao1 = False

    ao2 = _cd(s2).get("allow_overlap")
    if ao2 is not None and not isinstance(ao2, bool):
        sid2 = s2.get("id", "unknown")
        msg = f"Shape '{sid2}' has invalid customData.allow_overlap (expected bool, got {type(ao2).__name__}); treating as false."
        if warnings is not None and msg not in warnings:
            warnings.append(msg)
        ao2 = False

    if ao1 is True or ao2 is True:
        return True

    # Explicit group containment
    g1 = _get_group_ids(s1)
    g2 = _get_group_ids(s2)
    if g1 and g2 and (g1 & g2):
        return True

    id1 = s1.get("id")
    id2 = s2.get("id")
    s1_children = _cd(s1).get("child_element_ids", [])
    if not isinstance(s1_children, (list, tuple, set)):
        s1_children = []
    s2_children = _cd(s2).get("child_element_ids", [])
    if not isinstance(s2_children, (list, tuple, set)):
        s2_children = []

    # Guard relationship checks to require valid non-empty IDs to avoid None == None matching
    if id1 and id2:
        if id2 in s1_children or id1 in s2_children:
            return True
        if _cd(s1).get("parent_id") == id2 or _cd(s2).get("parent_id") == id1:
            return True
        if _cd(s1).get("container_id") == id2 or _cd(s2).get("container_id") == id1:
            return True

    x1_min = _coord(s1, "x")
    y1_min = _coord(s1, "y")
    w1 = abs(_coord(s1, "width"))
    h1 = abs(_coord(s1, "height"))
    x1_max = x1_min + w1
    y1_max = y1_min + h1

    x2_min = _coord(s2, "x")
    y2_min = _coord(s2, "y")
    w2 = abs(_coord(s2, "width"))
    h2 = abs(_coord(s2, "height"))
    x2_max = x2_min + w2
    y2_max = y2_min + h2

    # Geometrically nested: one shape is inside the other and substantially smaller
    area1, area2 = w1 * h1, w2 * h2
    if area1 > 0 and area2 > 0 and max(area1, area2) / min(area1, area2) >= 1.25:
        if area1 >= area2:
            if (
                x1_min <= x2_min + 2.0
                and y1_min <= y2_min + 2.0
                and x1_max >= x2_max - 2.0
                and y1_max >= y2_max - 2.0
            ):
                return True
        else:
            if (
                x2_min <= x1_min + 2.0
                and y2_min <= y1_min + 2.0
                and x2_max >= x1_max - 2.0
                and y2_max >= y1_max - 2.0
            ):
                return True

    return False


def _cap_warnings(warnings: list[str]) -> list[str]:
    """Cap warnings at 20 items, appending a truncation summary if exceeded."""
    if len(warnings) > 20:
        return warnings[:20] + [f"...and {len(warnings) - 20} more warnings."]
    return warnings


def _safe_wrap_and_measure(
    shape: dict[str, Any],
    text_el: dict[str, Any],
    target_w: float,
    warnings: list[str] | None = None,
) -> tuple[float, float, str]:
    """Safely wrap and measure text for a shape container, falling back and warning on failure."""
    raw_text = text_el.get("text") or ""
    raw_fs = text_el.get("fontSize")
    fs = int(raw_fs) if isinstance(raw_fs, (int, float)) and raw_fs > 0 else 20
    ff = text_el.get("fontFamily")
    stype = shape.get("type", "rectangle")
    sid = shape.get("id", "unknown")

    try:
        wrapped = wrap_text_to_shape(raw_text, shape=stype, target_w=target_w, font_size=fs, font_family=ff)
        tw, th, _ = measure_text_dimensions(wrapped, font_family=ff, font_size=fs)
        return tw, th, wrapped
    except (KeyError, ValueError, TypeError, OSError):
        tw = abs(_coord(text_el, "width"))
        th = abs(_coord(text_el, "height"))
        if warnings is not None:
            msg = f"Text containment skipped for shape '{sid}': could not measure text in font '{ff}'."
            if msg not in warnings:
                warnings.append(msg)
        return tw, th, raw_text


def measure_shape_text_containment(
    shape: dict[str, Any],
    text_el: dict[str, Any],
    warnings: list[str] | None = None,
) -> tuple[bool, float, float, float, float]:
    """Check if text overflows container geometry and compute required bounds.

    Returns:
        (is_clipped, req_w, req_h, deficit_w, deficit_h)
    """
    raw_text = text_el.get("text") or ""
    cur_w = abs(_coord(shape, "width"))
    cur_h = abs(_coord(shape, "height"))

    if not raw_text.strip():
        return False, round(cur_w, 1), round(cur_h, 1), 0.0, 0.0

    tw, th, _ = _safe_wrap_and_measure(shape, text_el, target_w=cur_w, warnings=warnings)

    stype = shape.get("type", "rectangle")
    min_w, min_h = required_container_size(stype, tw, th)
    req_w = max(cur_w, min_w)
    req_h = max(cur_h, min_h)

    deficit_w = max(0.0, req_w - cur_w)
    deficit_h = max(0.0, req_h - cur_h)
    is_clipped = deficit_w > 0.0 or deficit_h > 0.0
    return is_clipped, round(req_w, 1), round(req_h, 1), round(deficit_w, 1), round(deficit_h, 1)


def _compute_frame_depths(frames: list[dict[str, Any]]) -> dict[str, int]:
    """Compute nesting depth for each frame so innermost frames have highest depth."""
    frame_depths: dict[str, int] = {}
    frame_map = {f["id"]: f for f in frames if f.get("id")}
    for fid, f in frame_map.items():
        depth = 0
        curr = f.get("frameId")
        visited = {fid}
        while curr in frame_map and curr not in visited:
            depth += 1
            visited.add(curr)
            curr = frame_map[curr].get("frameId")
        frame_depths[fid] = depth
    return frame_depths


def diagnose_layout_issues(
    document_or_elements: Any,
    min_gap: float = 30.0,
    aggressiveness: str = "balanced",
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Detect and classify all layout defects in a scene with semantic distinction between defects and intentional geometry."""
    active, _ = _extract_active_elements(document_or_elements)
    if not active:
        return []

    gap_mult = AGGRESSIVENESS_MULT.get(aggressiveness, 1.0)
    effective_min_gap = min_gap * gap_mult

    valid_shapes = []
    for e in active:
        if e.get("type") in ("rectangle", "diamond", "ellipse") and not (_cd(e).get("type") in ("code_block_header",)):
            w = e.get("width")
            h = e.get("height")
            if (
                w is None
                or h is None
                or not isinstance(w, (int, float))
                or not isinstance(h, (int, float))
                or math.isnan(w)
                or math.isnan(h)
                or math.isinf(w)
                or math.isinf(h)
            ):
                sid = e.get("id", "unknown")
                msg = f"Skipped shape '{sid}': missing or non-finite width/height."
                if warnings is not None and msg not in warnings:
                    warnings.append(msg)
                continue
            valid_shapes.append(e)
    shapes = valid_shapes
    frames = [e for e in active if e.get("type") == "frame"]
    arrows = [e for e in active if e.get("type") in ("arrow", "line")]
    texts = [e for e in active if e.get("type") == "text"]

    bound_map: dict[str, dict[str, Any]] = {}
    for t in texts:
        cid = t.get("containerId")
        if cid:
            bound_map[cid] = t
    for s in shapes:
        sid = s.get("id")
        if sid and sid not in bound_map:
            raw_bound = s.get("boundElements")
            if isinstance(raw_bound, (list, tuple)):
                for b in raw_bound:
                    if isinstance(b, dict) and b.get("type") == "text":
                        tid = b.get("id")
                        matching_t = next((t for t in texts if t.get("id") == tid), None)
                        if matching_t:
                            bound_map[sid] = matching_t
                            break

    issues: list[dict[str, Any]] = []

    # 1. Text Containment & Clipping Detection
    for s in shapes:
        sid = s.get("id")
        if not sid:
            continue
        bound_t = bound_map.get(sid)
        if not bound_t:
            continue

        raw_text = bound_t.get("text") or ""
        if not raw_text.strip():
            continue

        cur_w = abs(_coord(s, "width"))
        cur_h = abs(_coord(s, "height"))

        is_clipped, req_w, req_h, deficit_w, deficit_h = measure_shape_text_containment(s, t)
        if is_clipped and (deficit_w > TEXT_DEFICIT_THRESHOLD_PX or deficit_h > TEXT_DEFICIT_THRESHOLD_PX):
            severity = "critical" if (deficit_w > 25.0 or deficit_h > 20.0) else "warning"
            issues.append(
                {
                    "id": f"text-clip-{sid}",
                    "type": "text_clipping",
                    "severity": severity,
                    "element_ids": [sid, t["id"]],
                    "description": f"Text in shape '{raw_text[:24]}...' overflows container by ({deficit_w}px w, {deficit_h}px h).",
                    "details": {
                        "shape_id": sid,
                        "text_id": t["id"],
                        "current_width": round(cur_w, 1),
                        "current_height": round(cur_h, 1),
                        "required_width": req_w,
                        "required_height": req_h,
                        "deficit_width": deficit_w,
                        "deficit_height": deficit_h,
                    },
                }
            )

    # 2. Node-to-Node Overlap Detection (Broadphase sweep-and-prune for O(N log N) scaling)
    sorted_diag_shapes = sorted(
        [s for s in shapes if s.get("id")],
        key=lambda s: _coord(s, "x")
    )
    for i in range(len(sorted_diag_shapes)):
        s1 = sorted_diag_shapes[i]
        id1 = s1["id"]

        x1_min = _coord(s1, "x")
        w1 = abs(_coord(s1, "width"))
        x1_max = x1_min + w1

        for j in range(i + 1, len(sorted_diag_shapes)):
            s2 = sorted_diag_shapes[j]
            x2_min = _coord(s2, "x")
            if x2_min >= x1_max - 1.0:
                break
            id2 = s2["id"]

            if is_intentional_overlap(s1, s2, warnings=warnings):
                continue

            y1_min = _coord(s1, "y")
            h1 = abs(_coord(s1, "height"))
            y1_max = y1_min + h1

            w2 = abs(_coord(s2, "width"))
            h2 = abs(_coord(s2, "height"))
            x2_max = x2_min + w2
            y2_min = _coord(s2, "y")
            y2_max = y2_min + h2

            inter_x = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
            inter_y = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))

            if inter_x > 1.0 and inter_y > 1.0:
                area = inter_x * inter_y
                min_area = max(1.0, min(w1 * h1, w2 * h2))
                overlap_ratio = area / min_area
                severity = "critical" if overlap_ratio > 0.15 else "warning"

                lbl1 = (bound_map.get(id1) or {}).get("text") or id1
                lbl2 = (bound_map.get(id2) or {}).get("text") or id2

                issues.append(
                    {
                        "id": f"overlap-{id1}-{id2}",
                        "type": "node_overlap",
                        "severity": severity,
                        "element_ids": [id1, id2],
                        "description": f"Collision between '{str(lbl1)[:20]}' and '{str(lbl2)[:20]}' ({round(inter_x, 1)}x{round(inter_y, 1)}px, ratio {round(overlap_ratio, 2)}).",
                        "details": {
                            "shape1_id": id1,
                            "shape2_id": id2,
                            "overlap_width": round(inter_x, 1),
                            "overlap_height": round(inter_y, 1),
                            "overlap_ratio": round(overlap_ratio, 2),
                        },
                    }
                )

    # 3. Frame Containment Violations (Supporting shapes, child frames, and standalone text; excluding connectors)
    frame_depths = _compute_frame_depths(frames)
    sorted_diag_frames = sorted(frames, key=lambda f: frame_depths.get(f.get("id", ""), 0), reverse=True)
    claimed_unparented_diag: set[str] = set()

    for f in sorted_diag_frames:
        fid = f.get("id")
        if not fid:
            continue
        fx = _coord(f, "x")
        fy = _coord(f, "y")
        fw = abs(_coord(f, "width"))
        fh = abs(_coord(f, "height"))
        f_right = fx + fw
        f_bottom = fy + fh
        fname = f.get("name") or fid

        # Candidate member children include shapes, child frames, and standalone text (excluding connectors and bound labels)
        children = [
            e
            for e in active
            if e.get("id") != fid
            and not e.get("containerId")
            and e.get("type") not in ("arrow", "line")
            and (
                e.get("frameId") == fid
                or (
                    e.get("type") != "frame"
                    and e.get("frameId") is None
                    and e.get("id")
                    and e.get("id") not in claimed_unparented_diag
                    and fx - 30.0 <= (_coord(e, "x") + abs(_coord(e, "width")) / 2.0) <= f_right + 30.0
                    and fy - 30.0 <= (_coord(e, "y") + abs(_coord(e, "height")) / 2.0) <= f_bottom + 150.0
                )
            )
        ]

        for c in children:
            if c.get("id") and c.get("frameId") is None:
                claimed_unparented_diag.add(c["id"])

        for c in children:
            cid = c.get("id")
            cx = _coord(c, "x")
            cy = _coord(c, "y")
            cw = abs(_coord(c, "width"))
            ch = abs(_coord(c, "height"))
            c_right = cx + cw
            c_bottom = cy + ch

            overflow_left = max(0.0, fx - cx)
            overflow_right = max(0.0, c_right - f_right)
            overflow_top = max(0.0, fy - cy)
            overflow_bottom = max(0.0, c_bottom - f_bottom)
            total_overflow = overflow_left + overflow_right + overflow_top + overflow_bottom

            if total_overflow > 2.0:
                bound_el = bound_map.get(cid) if cid else None
                clbl = (bound_el or {}).get("text") or c.get("name") or c.get("text") or cid or "unnamed"
                issues.append(
                    {
                        "id": f"containment-{fid}-{cid}",
                        "type": "frame_containment",
                        "severity": "warning",
                        "element_ids": [fid, cid],
                        "description": f"Component '{str(clbl)[:20]}' escapes frame '{fname}' boundaries by ({round(overflow_left + overflow_right, 1)}px horizontal, {round(overflow_top + overflow_bottom, 1)}px vertical).",
                        "details": {
                            "frame_id": fid,
                            "shape_id": cid,
                            "overflow_x": round(overflow_left + overflow_right, 1),
                            "overflow_y": round(overflow_top + overflow_bottom, 1),
                        },
                    }
                )

    # 4. Connector Collisions with Unrelated Obstacle Shapes
    collided_pairs: set[tuple[str, str]] = set()
    for a in arrows:
        aid = a.get("id")
        if not aid:
            continue
        start_bind = a.get("startBinding")
        sb = start_bind.get("elementId") if isinstance(start_bind, dict) else None
        end_bind = a.get("endBinding")
        eb = end_bind.get("elementId") if isinstance(end_bind, dict) else None

        ax = _coord(a, "x")
        ay = _coord(a, "y")
        raw_pts = a.get("points")
        if isinstance(raw_pts, (list, tuple)) and len(raw_pts) >= 2:
            parsed_pts = []
            for p in raw_pts:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    try:
                        px, py = float(p[0]), float(p[1])
                        if math.isfinite(px) and math.isfinite(py):
                            parsed_pts.append((px, py))
                    except (ValueError, TypeError):
                        continue
            pts = parsed_pts if len(parsed_pts) >= 2 else [(0.0, 0.0), (abs(_coord(a, "width")), abs(_coord(a, "height")))]
        else:
            pts = [(0.0, 0.0), (abs(_coord(a, "width")), abs(_coord(a, "height")))]

        world_pts = [(ax + p[0], ay + p[1]) for p in pts]

        for k in range(len(world_pts) - 1):
            p1 = world_pts[k]
            p2 = world_pts[k + 1]

            for s in shapes:
                sid = s.get("id")
                if not sid or sid in (sb, eb) or _cd(s).get("allow_overlap") is True:
                    continue
                if (aid, sid) in collided_pairs:
                    continue

                sx = _coord(s, "x")
                sy = _coord(s, "y")
                sw = abs(_coord(s, "width"))
                sh = abs(_coord(s, "height"))

                if segment_intersects_rect(p1, p2, (sx, sy, sx + sw, sy + sh), margin=2.0):
                    collided_pairs.add((aid, sid))
                    slbl = (bound_map.get(sid) or {}).get("text") or sid
                    issues.append(
                        {
                            "id": f"collision-{aid}-{sid}",
                            "type": "connector_collision",
                            "severity": "warning",
                            "element_ids": [aid, sid],
                            "description": f"Connector line '{aid}' passes through unrelated component '{str(slbl)[:20]}'.",
                            "details": {
                                "arrow_id": aid,
                                "obstacle_id": sid,
                                "source_id": sb,
                                "target_id": eb,
                            },
                        }
                    )
                    break

    # 5. Inconsistent Spacing Violations (Crowded Elements)
    max_spacing_gap = effective_min_gap * SPACING_RATIO_THRESHOLD
    for i in range(len(sorted_diag_shapes)):
        s1 = sorted_diag_shapes[i]
        id1 = s1["id"]
        x1_min = _coord(s1, "x")
        w1 = abs(_coord(s1, "width"))
        x1_max = x1_min + w1
        y1_min = _coord(s1, "y")
        y1_max = y1_min + abs(_coord(s1, "height"))

        for j in range(i + 1, len(sorted_diag_shapes)):
            s2 = sorted_diag_shapes[j]
            x2_min = _coord(s2, "x")
            if x2_min >= x1_max + max_spacing_gap:
                break
            id2 = s2["id"]

            if is_intentional_overlap(s1, s2, warnings=warnings):
                continue

            y2_min = _coord(s2, "y")
            x2_max = x2_min + abs(_coord(s2, "width"))
            y2_max = y2_min + abs(_coord(s2, "height"))

            # Check if elements are horizontally aligned
            v_overlap = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))
            if v_overlap > 10.0:
                h_gap = max(x1_min, x2_min) - min(x1_max, x2_max)
                if 0.5 < h_gap < max_spacing_gap:
                    lbl1 = (bound_map.get(id1) or {}).get("text") or id1
                    lbl2 = (bound_map.get(id2) or {}).get("text") or id2
                    issues.append(
                        {
                            "id": f"spacing-h-{id1}-{id2}",
                            "type": "inconsistent_spacing",
                            "severity": "info",
                            "element_ids": [id1, id2],
                            "description": f"Sub-optimal horizontal gap between '{str(lbl1)[:20]}' and '{str(lbl2)[:20]}' ({round(h_gap, 1)}px < min {min_gap}px).",
                            "details": {"shape1_id": id1, "shape2_id": id2, "gap": round(h_gap, 1), "min_gap": min_gap},
                        }
                    )

            # Check if elements are vertically aligned
            h_overlap = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
            if h_overlap > 10.0:
                v_gap = max(y1_min, y2_min) - min(y1_max, y2_max)
                if 0.5 < v_gap < max_spacing_gap:
                    lbl1 = (bound_map.get(id1) or {}).get("text") or id1
                    lbl2 = (bound_map.get(id2) or {}).get("text") or id2
                    issues.append(
                        {
                            "id": f"spacing-v-{id1}-{id2}",
                            "type": "inconsistent_spacing",
                            "severity": "info",
                            "element_ids": [id1, id2],
                            "description": f"Sub-optimal vertical gap between '{str(lbl1)[:20]}' and '{str(lbl2)[:20]}' ({round(v_gap, 1)}px < min {min_gap}px).",
                            "details": {"shape1_id": id1, "shape2_id": id2, "gap": round(v_gap, 1), "min_gap": min_gap},
                        }
                    )

    return issues


def summarize_planned_repairs(
    document_or_elements: Any,
    issues: list[dict[str, Any]],
    repair_scope: str = "all",
    aggressiveness: str = "balanced",
    min_gap: float = 30.0,
) -> list[dict[str, Any]]:
    """Summarize intended repairs for detected layout defects before mutation.

    This provides a high-level summary of intended transformations and is not an executable plan.
    """
    scope, aggr, m_gap = _validate_params(repair_scope, aggressiveness, min_gap)
    gap_mult = AGGRESSIVENESS_MULT[aggr]
    effective_min_gap = m_gap * gap_mult

    active, _ = _extract_active_elements(document_or_elements)
    element_index = {e["id"]: e for e in active if e.get("id")}
    planned_changes: list[dict[str, Any]] = []

    allowed_types = {
        "all": {"text_clipping", "node_overlap", "frame_containment", "connector_collision", "inconsistent_spacing"},
        "overlaps": {"node_overlap"},
        "connectors": {"connector_collision"},
        "containment": {"frame_containment"},
        "text": {"text_clipping"},
        "spacing": {"inconsistent_spacing"},
    }[scope]

    # Phase 1: Text Clipping Plans
    if "text_clipping" in allowed_types:
        for issue in issues:
            if issue["type"] == "text_clipping":
                sid = issue["details"]["shape_id"]
                s = element_index.get(sid)
                if s and not s.get("locked"):
                    planned_changes.append(
                        {
                            "phase": "text_containment",
                            "element_id": sid,
                            "action": "resize_container",
                            "description": f"Expand container '{sid}' to fit enclosed text ({issue['details']['required_width']}x{issue['details']['required_height']}px).",
                            "parameters": {
                                "target_width": issue["details"]["required_width"],
                                "target_height": issue["details"]["required_height"],
                            },
                        }
                    )

    # Phase 2: Overlap Resolution Plans
    if "node_overlap" in allowed_types:
        for issue in issues:
            if issue["type"] == "node_overlap":
                id1 = issue["details"]["shape1_id"]
                id2 = issue["details"]["shape2_id"]
                s1 = element_index.get(id1)
                s2 = element_index.get(id2)
                if s1 and s2:
                    cluster1 = _get_shape_cluster(s1, active)
                    cluster2 = _get_shape_cluster(s2, active)
                    c1_locked = _is_cluster_locked(cluster1)
                    c2_locked = _is_cluster_locked(cluster2)
                    if c1_locked and c2_locked:
                        continue

                    if c2_locked and not c1_locked:
                        target_id = id1
                    elif c1_locked and not c2_locked:
                        target_id = id2
                    elif _coord(s2, "y") > _coord(s1, "y") or (
                        _coord(s2, "y") == _coord(s1, "y") and _coord(s2, "x") >= _coord(s1, "x")
                    ):
                        target_id = id2
                    else:
                        target_id = id1

                    planned_changes.append(
                        {
                            "phase": "node_overlap",
                            "element_id": target_id,
                            "action": "shift_node",
                            "description": f"Displace node '{target_id}' to eliminate overlap with peer.",
                            "parameters": {
                                "overlap_width": issue["details"]["overlap_width"],
                                "overlap_height": issue["details"]["overlap_height"],
                            },
                        }
                    )

    # Phase 3: Frame Containment Expansion Plans
    if "frame_containment" in allowed_types:
        planned_frame_ids = set()
        for issue in issues:
            if issue["type"] == "frame_containment":
                fid = issue["details"]["frame_id"]
                f_el = element_index.get(fid)
                if fid not in planned_frame_ids and f_el and not f_el.get("locked"):
                    planned_frame_ids.add(fid)
                    planned_changes.append(
                        {
                            "phase": "frame_containment",
                            "element_id": fid,
                            "action": "expand_frame",
                            "description": f"Expand frame '{fid}' boundaries to fully encompass child components.",
                            "parameters": {
                                "overflow_x": issue["details"]["overflow_x"],
                                "overflow_y": issue["details"]["overflow_y"],
                            },
                        }
                    )

    # Phase 4: Connector Routing Plans
    if "connector_collision" in allowed_types:
        routed_arrows = set()
        for issue in issues:
            if issue["type"] == "connector_collision":
                aid = issue["details"]["arrow_id"]
                a_el = element_index.get(aid)
                if aid not in routed_arrows and a_el and not a_el.get("locked"):
                    routed_arrows.add(aid)
                    planned_changes.append(
                        {
                            "phase": "connector_routing",
                            "element_id": aid,
                            "action": "reroute_connector",
                            "description": f"Reroute connector '{aid}' with obstacle-avoiding orthogonal paths.",
                            "parameters": {"clearance": round(15.0 * gap_mult, 1)},
                        }
                    )

    # Phase 5: Spacing Adjustment Plans
    if "inconsistent_spacing" in allowed_types:
        for issue in issues:
            if issue["type"] == "inconsistent_spacing":
                id1 = issue["details"]["shape1_id"]
                id2 = issue["details"]["shape2_id"]
                s1 = element_index.get(id1)
                s2 = element_index.get(id2)
                if s1 and s2:
                    cluster1 = _get_shape_cluster(s1, active)
                    cluster2 = _get_shape_cluster(s2, active)
                    c1_locked = _is_cluster_locked(cluster1)
                    c2_locked = _is_cluster_locked(cluster2)
                    if c1_locked and c2_locked:
                        continue

                    if c2_locked and not c1_locked:
                        target_id = id1
                    elif c1_locked and not c2_locked:
                        target_id = id2
                    elif _coord(s2, "y") > _coord(s1, "y") or (
                        _coord(s2, "y") == _coord(s1, "y") and _coord(s2, "x") >= _coord(s1, "x")
                    ):
                        target_id = id2
                    else:
                        target_id = id1
                    planned_changes.append(
                        {
                            "phase": "spacing_adjustment",
                            "element_id": target_id,
                            "action": "adjust_spacing",
                            "description": f"Adjust spacing for component '{target_id}' to achieve minimum gap ({round(effective_min_gap, 1)}px).",
                            "parameters": {
                                "current_gap": issue["details"]["gap"],
                                "min_gap": round(effective_min_gap, 1),
                            },
                        }
                    )

    deduped_plans: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for pc in planned_changes:
        key = (pc.get("phase", ""), str(pc.get("element_id", "")))
        if key not in seen:
            seen.add(key)
            deduped_plans.append(pc)

    return deduped_plans


plan_layout_repairs = summarize_planned_repairs


def _expand_frames_to_contain_children(
    frames: list[dict[str, Any]],
    active: list[dict[str, Any]],
    gap_mult: float,
    applied_changes: list[dict[str, Any]],
    skipped_repairs: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
) -> bool:
    """Expand frames to encompass all direct and indirect children in bottom-up topological depth order."""
    frame_padding = 30.0 * gap_mult
    header_pad = 25.0
    frame_depths = _compute_frame_depths(frames)
    sorted_frames = sorted(frames, key=lambda f: frame_depths.get(f.get("id", ""), 0), reverse=True)

    any_frame_expanded = False

    for _frame_pass in range(3):
        pass_changed = False
        claimed_unparented: set[str] = set()

        for f in sorted_frames:
            fid = f.get("id")
            if not fid:
                continue

            if f.get("locked"):
                if skipped_repairs is not None:
                    if not any(sr["element_id"] == fid for sr in skipped_repairs):
                        skipped_repairs.append(
                            {"element_id": fid, "reason": "Frame is locked and cannot be expanded."}
                        )
                if warnings is not None:
                    msg = f"Skipped expanding locked frame '{fid}'."
                    if msg not in warnings:
                        warnings.append(msg)
                continue

            children = [
                e
                for e in active
                if e.get("id") != fid
                and not e.get("containerId")
                and e.get("type") not in ("arrow", "line")
                and (
                    e.get("frameId") == fid
                    or (
                        e.get("type") != "frame"
                        and e.get("frameId") is None
                        and e.get("id")
                        and e.get("id") not in claimed_unparented
                        and _coord(f, "x") - 30.0 <= (_coord(e, "x") + abs(_coord(e, "width")) / 2.0) <= _coord(f, "x") + abs(_coord(f, "width")) + 30.0
                        and _coord(f, "y") - 30.0 <= (_coord(e, "y") + abs(_coord(e, "height")) / 2.0) <= _coord(f, "y") + abs(_coord(f, "height")) + 150.0
                    )
                )
            ]

            for c in children:
                if c.get("id") and c.get("frameId") is None:
                    claimed_unparented.add(c["id"])

            if not children:
                continue

            fx = _coord(f, "x")
            fy = _coord(f, "y")
            fw = abs(_coord(f, "width"))
            fh = abs(_coord(f, "height"))
            f_right = fx + fw
            f_bottom = fy + fh

            overflow_detected = any(
                _coord(s, "x") < fx
                or _coord(s, "x") + abs(_coord(s, "width")) > f_right
                or _coord(s, "y") < fy
                or _coord(s, "y") + abs(_coord(s, "height")) > f_bottom
                for s in children
            )
            if not overflow_detected:
                continue

            old_f_state = {
                "x": f.get("x"),
                "y": f.get("y"),
                "width": f.get("width"),
                "height": f.get("height"),
            }

            min_c_x = min(_coord(s, "x") for s in children) - frame_padding
            min_c_y = min(_coord(s, "y") for s in children) - frame_padding - header_pad
            max_c_x = max(_coord(s, "x") + abs(_coord(s, "width")) for s in children) + frame_padding
            max_c_y = max(_coord(s, "y") + abs(_coord(s, "height")) for s in children) + frame_padding

            new_fx = min(fx, min_c_x)
            new_fy = min(fy, min_c_y)
            new_right = max(f_right, max_c_x)
            new_bottom = max(f_bottom, max_c_y)
            new_fw = new_right - new_fx
            new_fh = new_bottom - new_fy

            if (
                abs(new_fx - _coord(f, "x")) > 0.5
                or abs(new_fy - _coord(f, "y")) > 0.5
                or abs(new_fw - abs(_coord(f, "width"))) > 0.5
                or abs(new_fh - abs(_coord(f, "height"))) > 0.5
            ):
                f["x"] = round(new_fx, 1)
                f["y"] = round(new_fy, 1)
                f["width"] = round(new_fw, 1)
                f["height"] = round(new_fh, 1)

                applied_changes.append(
                    {
                        "element_id": fid,
                        "change_type": "expand_frame",
                        "description": f"Expanded frame '{fid}' to fully contain its child elements.",
                        "before": old_f_state,
                        "after": {"x": f["x"], "y": f["y"], "width": f["width"], "height": f["height"]},
                    }
                )

                for c in children:
                    cid = c.get("id")
                    if cid and c.get("frameId") is None:
                        c["frameId"] = fid
                        applied_changes.append(
                            {
                                "element_id": cid,
                                "change_type": "reparent",
                                "description": f"Assigned unparented element '{cid}' to frame '{fid}'.",
                                "before": {"frameId": None},
                                "after": {"frameId": fid},
                            }
                        )

                pass_changed = True
                any_frame_expanded = True

        if not pass_changed:
            break

    return any_frame_expanded


def _resolve_node_overlaps(
    shapes: list[dict[str, Any]],
    effective_min_gap: float,
    bound_map: dict[str, dict[str, Any]],
    applied_changes: list[dict[str, Any]],
    skipped_repairs: list[dict[str, Any]],
    warnings: list[str],
) -> bool:
    """Resolve node overlaps using up to 12 passes. Returns True if any elements were moved."""
    any_moved = False
    for _pass in range(12):
        had_overlap = False
        group_index = _build_group_index(shapes)
        sorted_shapes = sorted(
            shapes,
            key=lambda s: (str(s.get("frameId") or ""), _coord(s, "y"), _coord(s, "x")),
        )

        for i in range(len(sorted_shapes)):
            s1 = sorted_shapes[i]
            id1 = s1.get("id")
            x1_min, y1_min = _coord(s1, "x"), _coord(s1, "y")
            x1_max, y1_max = x1_min + abs(_coord(s1, "width")), y1_min + abs(_coord(s1, "height"))
            s1_frame = str(s1.get("frameId") or "")

            for j in range(i + 1, len(sorted_shapes)):
                s2 = sorted_shapes[j]
                if str(s2.get("frameId") or "") == s1_frame and _coord(s2, "y") >= y1_max:
                    break
                id2 = s2.get("id")

                if is_intentional_overlap(s1, s2, warnings=warnings):
                    continue

                x2_min, y2_min = _coord(s2, "x"), _coord(s2, "y")
                x2_max, y2_max = x2_min + abs(_coord(s2, "width")), y2_min + abs(_coord(s2, "height"))

                ix = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
                iy = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))

                if ix > 0.5 and iy > 0.5:
                    had_overlap = True

                    cluster1 = _get_shape_cluster(s1, group_index)
                    cluster2 = _get_shape_cluster(s2, group_index)

                    c1_locked = _is_cluster_locked(cluster1)
                    c2_locked = _is_cluster_locked(cluster2)

                    if c1_locked and c2_locked:
                        if not any(sr.get("element_id") == id2 for sr in skipped_repairs):
                            skipped_repairs.append(
                                {"element_id": id2 or "unknown", "reason": "Both colliding clusters contain locked elements and cannot be displaced."}
                            )
                        msg = f"Cannot resolve collision between locked clusters '{id1}' and '{id2}'."
                        if msg not in warnings:
                            warnings.append(msg)
                        continue

                    if c2_locked and not c1_locked:
                        target_cluster = cluster1
                        ref_cluster = cluster2
                    else:
                        target_cluster = cluster2
                        ref_cluster = cluster1

                    t_x_min = min(_coord(s, "x") for s in target_cluster)
                    t_x_max = max(_coord(s, "x") + abs(_coord(s, "width")) for s in target_cluster)
                    t_y_min = min(_coord(s, "y") for s in target_cluster)
                    t_y_max = max(_coord(s, "y") + abs(_coord(s, "height")) for s in target_cluster)

                    r_x_min = min(_coord(s, "x") for s in ref_cluster)
                    r_x_max = max(_coord(s, "x") + abs(_coord(s, "width")) for s in ref_cluster)
                    r_y_min = min(_coord(s, "y") for s in ref_cluster)
                    r_y_max = max(_coord(s, "y") + abs(_coord(s, "height")) for s in ref_cluster)

                    if t_x_min >= r_x_min:
                        dx = r_x_max - t_x_min + effective_min_gap
                    else:
                        dx = -(t_x_max - r_x_min + effective_min_gap)

                    if t_y_min >= r_y_min:
                        dy = r_y_max - t_y_min + effective_min_gap
                    else:
                        dy = -(t_y_max - r_y_min + effective_min_gap)

                    if abs(dx) <= abs(dy):
                        shift_dx, shift_dy = dx, 0.0
                    else:
                        shift_dx, shift_dy = 0.0, dy

                    for target_shape in target_cluster:
                        tid = target_shape.get("id")
                        if not tid:
                            continue
                        old_state_target = {"x": target_shape.get("x"), "y": target_shape.get("y")}
                        new_x = round(_coord(target_shape, "x") + shift_dx, 1)
                        new_y = round(_coord(target_shape, "y") + shift_dy, 1)
                        target_shape["x"] = new_x
                        target_shape["y"] = new_y

                        t_lbl = bound_map.get(tid)
                        if t_lbl:
                            t_lbl["x"] = round(_coord(t_lbl, "x") + shift_dx, 1)
                            t_lbl["y"] = round(_coord(t_lbl, "y") + shift_dy, 1)

                        applied_changes.append(
                            {
                                "element_id": tid,
                                "change_type": "move",
                                "description": f"Shifted node '{tid}' by (dx={shift_dx:.1f}, dy={shift_dy:.1f}) to clear overlap.",
                                "before": old_state_target,
                                "after": {"x": target_shape["x"], "y": target_shape["y"]},
                            }
                        )
                        any_moved = True

        if not had_overlap:
            break

    return any_moved


def apply_layout_repairs(
    document_or_elements: Any,
    repair_scope: str = "all",
    aggressiveness: str = "balanced",
    min_gap: float = 30.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Deterministically execute repair transformations on scene elements in strict topological phases.

    Returns:
        (elements, applied_changes, skipped_repairs, warnings)
    """
    scope, aggr, m_gap = _validate_params(repair_scope, aggressiveness, min_gap)
    gap_mult = AGGRESSIVENESS_MULT[aggr]
    effective_min_gap = m_gap * gap_mult

    if isinstance(document_or_elements, dict) and "elements" in document_or_elements:
        elements = document_or_elements["elements"]
    elif isinstance(document_or_elements, list):
        elements = document_or_elements
    else:
        raise SceneError("Expected document dictionary or list of elements")

    allowed_types = {
        "all": {"text", "overlaps", "containment", "connectors", "spacing"},
        "overlaps": {"overlaps"},
        "connectors": {"connectors"},
        "containment": {"containment"},
        "text": {"text"},
        "spacing": {"spacing"},
    }[scope]

    active = [e for e in elements if isinstance(e, dict) and not e.get("isDeleted")]
    shapes = [
        e
        for e in active
        if e.get("type") in ("rectangle", "diamond", "ellipse")
        and not (_cd(e).get("type") in ("code_block_header",))
    ]
    frames = [e for e in active if e.get("type") == "frame"]
    arrows = [e for e in active if e.get("type") in ("arrow", "line")]
    texts = [e for e in active if e.get("type") == "text"]

    bound_map: dict[str, dict[str, Any]] = {}
    for t in texts:
        cid = t.get("containerId")
        if cid:
            bound_map[cid] = t
    for s in shapes:
        sid = s.get("id")
        if sid and sid not in bound_map:
            raw_bound = s.get("boundElements")
            if isinstance(raw_bound, (list, tuple)):
                for b in raw_bound:
                    if isinstance(b, dict) and b.get("type") == "text":
                        tid = b.get("id")
                        matching_t = next((t for t in texts if t.get("id") == tid), None)
                        if matching_t:
                            bound_map[sid] = matching_t
                            break

    applied_changes: list[dict[str, Any]] = []
    skipped_repairs: list[dict[str, Any]] = []
    warnings: list[str] = []

    # =========================================================================
    # Phase 1: Text Containment & Box Resizing (Center-Outward Expansion)
    # =========================================================================
    if "text" in allowed_types:
        for s in shapes:
            sid = s.get("id")
            if not sid:
                continue
            if s.get("locked"):
                skipped_repairs.append({"element_id": sid, "reason": "Element is locked and cannot be resized."})
                warnings.append(f"Skipped resizing locked container '{sid}'.")
                continue

            bound_t = bound_map.get(sid)
            if not bound_t:
                continue

            raw_text = bound_t.get("text") or ""
            if not raw_text.strip():
                continue

            is_clipped, req_w, req_h, deficit_w, deficit_h = measure_shape_text_containment(s, t, warnings=warnings)
            if is_clipped and (deficit_w > TEXT_DEFICIT_THRESHOLD_PX or deficit_h > TEXT_DEFICIT_THRESHOLD_PX):
                cur_w = abs(_coord(s, "width"))
                cur_h = abs(_coord(s, "height"))
                old_state = {"x": s.get("x"), "y": s.get("y"), "width": cur_w, "height": cur_h}
                new_w = max(cur_w, req_w)
                new_h = max(cur_h, req_h)

                # Expand outward from center to preserve spatial alignment
                cx = _coord(s, "x") + cur_w / 2.0
                cy = _coord(s, "y") + cur_h / 2.0
                new_x = cx - new_w / 2.0
                new_y = cy - new_h / 2.0

                s["x"] = round(new_x, 1)
                s["y"] = round(new_y, 1)
                s["width"] = round(new_w, 1)
                s["height"] = round(new_h, 1)

                # Re-center bound text inside expanded container
                tw, th, wrapped = _safe_wrap_and_measure(s, t, target_w=new_w, warnings=warnings)

                t["x"] = round(cx - tw / 2.0, 1)
                t["y"] = round(cy - th / 2.0, 1)
                t["width"] = round(tw, 1)
                t["height"] = round(th, 1)

                applied_changes.append(
                    {
                        "element_id": sid,
                        "change_type": "resize",
                        "description": f"Expanded container '{sid}' outward to contain text lines without clipping.",
                        "before": old_state,
                        "after": {"x": s["x"], "y": s["y"], "width": s["width"], "height": s["height"]},
                    }
                )

    # =========================================================================
    # Phase 2: Node Overlap Resolution (Minimal Displacement with Grouping)
    # =========================================================================
    if "overlaps" in allowed_types:
        _resolve_node_overlaps(
            shapes,
            effective_min_gap,
            bound_map,
            applied_changes,
            skipped_repairs,
            warnings,
        )

    # =========================================================================
    # Phase 3: Frame Containment Expansion
    # =========================================================================
    if "containment" in allowed_types and frames:
        _expand_frames_to_contain_children(
            frames,
            active,
            gap_mult,
            applied_changes,
            skipped_repairs=skipped_repairs,
            warnings=warnings,
        )

    # =========================================================================
    # Phase 4: Connector Rerouting & Obstacle Avoidance
    # =========================================================================
    if "connectors" in allowed_types and arrows:
        arrows_snapshot = {
            a["id"]: {
                "points": deepcopy(a.get("points")),
                "x": a.get("x"),
                "y": a.get("y"),
            }
            for a in arrows
            if a.get("id")
        }

        for a in arrows:
            if a.get("locked"):
                aid = a.get("id", "unknown")
                if not any(sr.get("element_id") == aid for sr in skipped_repairs):
                    skipped_repairs.append({"element_id": aid, "reason": "Connector is locked and cannot be rerouted."})
                msg = f"Skipped rerouting locked connector '{aid}'."
                if msg not in warnings:
                    warnings.append(msg)

        reroute_scene_arrows(active, clearance=15.0 * gap_mult, lane_spacing=24.0)

        for a in arrows:
            aid = a.get("id")
            if not aid or a.get("locked"):
                continue
            snap = arrows_snapshot.get(aid, {})
            if a.get("points") != snap.get("points") or a.get("x") != snap.get("x") or a.get("y") != snap.get("y"):
                applied_changes.append(
                    {
                        "element_id": aid,
                        "change_type": "reroute",
                        "description": f"Recalculated obstacle-aware orthogonal path for connector '{aid}'.",
                        "before": {"points": snap.get("points"), "x": snap.get("x"), "y": snap.get("y")},
                        "after": {"points": a.get("points"), "x": a.get("x"), "y": a.get("y"), "elbowed": a.get("elbowed")},
                    }
                )

    # =========================================================================
    # Phase 5: Spacing Adjustments for Crowded Components (Cascading Displacements)
    # =========================================================================
    if "spacing" in allowed_types:
        moved_shapes = False

        for _pass in range(12):
            pass_moved = False
            group_index = _build_group_index(shapes)

            # 5a. Horizontal Spacing Adjustments (Left to Right Cascade)
            max_spacing_gap = effective_min_gap * SPACING_RATIO_THRESHOLD
            h_shapes = sorted(shapes, key=lambda s: _coord(s, "x"))
            for i in range(len(h_shapes) - 1):
                s1 = h_shapes[i]
                id1 = s1.get("id")
                x1_max = _coord(s1, "x") + abs(_coord(s1, "width"))
                y1_min = _coord(s1, "y")
                y1_max = y1_min + abs(_coord(s1, "height"))

                for j in range(i + 1, len(h_shapes)):
                    s2 = h_shapes[j]
                    x2_min = _coord(s2, "x")
                    if x2_min >= x1_max + max_spacing_gap:
                        break
                    id2 = s2.get("id")

                    if is_intentional_overlap(s1, s2, warnings=warnings):
                        continue

                    y2_min = _coord(s2, "y")
                    y2_max = y2_min + abs(_coord(s2, "height"))

                    v_overlap = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))
                    if v_overlap > 10.0:
                        h_gap = x2_min - x1_max

                        if h_gap < effective_min_gap * SPACING_RATIO_THRESHOLD:
                            cluster1 = _get_shape_cluster(s1, group_index)
                            cluster2 = _get_shape_cluster(s2, group_index)
                            c1_locked = _is_cluster_locked(cluster1)
                            c2_locked = _is_cluster_locked(cluster2)

                            if c1_locked and c2_locked:
                                if not any(sr.get("element_id") == id2 for sr in skipped_repairs):
                                    skipped_repairs.append(
                                        {"element_id": id2 or "unknown", "reason": "Both crowded clusters contain locked elements and cannot be adjusted."}
                                    )
                                msg = f"Cannot adjust horizontal spacing between locked clusters '{id1}' and '{id2}'."
                                if msg not in warnings:
                                    warnings.append(msg)
                                continue

                            if c2_locked and not c1_locked:
                                # Shift cluster1 leftward to open required gap
                                new_x1 = round(x2_min - effective_min_gap - abs(_coord(s1, "width")), 1)
                                delta = round(new_x1 - _coord(s1, "x"), 1)
                                if abs(delta) > 0.5:
                                    for shape_to_move in cluster1:
                                        sid = shape_to_move.get("id")
                                        if not sid:
                                            continue
                                        old_pos = {"x": shape_to_move.get("x"), "y": shape_to_move.get("y")}
                                        shape_to_move["x"] = round(_coord(shape_to_move, "x") + delta, 1)
                                        pt = bound_map.get(sid)
                                        if pt:
                                            pt["x"] = round(_coord(pt, "x") + delta, 1)
                                        applied_changes.append(
                                            {
                                                "element_id": sid,
                                                "change_type": "adjust_spacing",
                                                "description": f"Adjusted horizontal spacing for node '{sid}' by {delta}px.",
                                                "before": old_pos,
                                                "after": {"x": shape_to_move["x"], "y": shape_to_move["y"]},
                                            }
                                        )
                                    pass_moved = True
                            else:
                                # Shift cluster2 rightward
                                new_x2 = round(x1_max + effective_min_gap, 1)
                                delta = round(new_x2 - x2_min, 1)
                                if delta > 0.5:
                                    for shape_to_move in cluster2:
                                        sid = shape_to_move.get("id")
                                        if not sid:
                                            continue
                                        old_pos = {"x": shape_to_move.get("x"), "y": shape_to_move.get("y")}
                                        shape_to_move["x"] = round(_coord(shape_to_move, "x") + delta, 1)
                                        pt = bound_map.get(sid)
                                        if pt:
                                            pt["x"] = round(_coord(pt, "x") + delta, 1)
                                        applied_changes.append(
                                            {
                                                "element_id": sid,
                                                "change_type": "adjust_spacing",
                                                "description": f"Adjusted horizontal spacing for node '{sid}' by {delta}px.",
                                                "before": old_pos,
                                                "after": {"x": shape_to_move["x"], "y": shape_to_move["y"]},
                                            }
                                        )
                                    pass_moved = True

            # 5b. Vertical Spacing Adjustments (Top to Bottom Cascade)
            v_shapes = sorted(shapes, key=lambda s: _coord(s, "y"))
            for i in range(len(v_shapes) - 1):
                s1 = v_shapes[i]
                id1 = s1.get("id")
                y1_max = _coord(s1, "y") + abs(_coord(s1, "height"))
                x1_min = _coord(s1, "x")
                x1_max = x1_min + abs(_coord(s1, "width"))

                for j in range(i + 1, len(v_shapes)):
                    s2 = v_shapes[j]
                    y2_min = _coord(s2, "y")
                    if y2_min >= y1_max + max_spacing_gap:
                        break
                    id2 = s2.get("id")

                    if is_intentional_overlap(s1, s2, warnings=warnings):
                        continue

                    x2_min = _coord(s2, "x")
                    x2_max = x2_min + abs(_coord(s2, "width"))

                    h_overlap = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
                    if h_overlap > 10.0:
                        v_gap = y2_min - y1_max

                        if v_gap < effective_min_gap * SPACING_RATIO_THRESHOLD:
                            cluster1 = _get_shape_cluster(s1, group_index)
                            cluster2 = _get_shape_cluster(s2, group_index)
                            c1_locked = _is_cluster_locked(cluster1)
                            c2_locked = _is_cluster_locked(cluster2)

                            if c1_locked and c2_locked:
                                if not any(sr.get("element_id") == id2 for sr in skipped_repairs):
                                    skipped_repairs.append(
                                        {"element_id": id2 or "unknown", "reason": "Both crowded clusters contain locked elements and cannot be adjusted."}
                                    )
                                msg = f"Cannot adjust vertical spacing between locked clusters '{id1}' and '{id2}'."
                                if msg not in warnings:
                                    warnings.append(msg)
                                continue

                            if c2_locked and not c1_locked:
                                # Shift cluster1 upward
                                new_y1 = round(y2_min - effective_min_gap - abs(_coord(s1, "height")), 1)
                                delta = round(new_y1 - _coord(s1, "y"), 1)
                                if abs(delta) > 0.5:
                                    for shape_to_move in cluster1:
                                        sid = shape_to_move.get("id")
                                        if not sid:
                                            continue
                                        old_pos = {"x": shape_to_move.get("x"), "y": shape_to_move.get("y")}
                                        shape_to_move["y"] = round(_coord(shape_to_move, "y") + delta, 1)
                                        pt = bound_map.get(sid)
                                        if pt:
                                            pt["y"] = round(_coord(pt, "y") + delta, 1)
                                        applied_changes.append(
                                            {
                                                "element_id": sid,
                                                "change_type": "adjust_spacing",
                                                "description": f"Adjusted vertical spacing for node '{sid}' by {delta}px.",
                                                "before": old_pos,
                                                "after": {"x": shape_to_move["x"], "y": shape_to_move["y"]},
                                            }
                                        )
                                    pass_moved = True
                            else:
                                # Shift cluster2 downward
                                new_y2 = round(y1_max + effective_min_gap, 1)
                                delta = round(new_y2 - y2_min, 1)
                                if delta > 0.5:
                                    for shape_to_move in cluster2:
                                        sid = shape_to_move.get("id")
                                        if not sid:
                                            continue
                                        old_pos = {"x": shape_to_move.get("x"), "y": shape_to_move.get("y")}
                                        shape_to_move["y"] = round(_coord(shape_to_move, "y") + delta, 1)
                                        pt = bound_map.get(sid)
                                        if pt:
                                            pt["y"] = round(_coord(pt, "y") + delta, 1)
                                        applied_changes.append(
                                            {
                                                "element_id": sid,
                                                "change_type": "adjust_spacing",
                                                "description": f"Adjusted vertical spacing for node '{sid}' by {delta}px.",
                                                "before": old_pos,
                                                "after": {"x": shape_to_move["x"], "y": shape_to_move["y"]},
                                            }
                                        )
                                    pass_moved = True

            if pass_moved:
                moved_shapes = True
                if "overlaps" in allowed_types:
                    _resolve_node_overlaps(
                        shapes,
                        effective_min_gap,
                        bound_map,
                        applied_changes,
                        skipped_repairs,
                        warnings,
                    )
            else:
                break

        if moved_shapes:
            if frames:
                _expand_frames_to_contain_children(
                    frames,
                    active,
                    gap_mult,
                    applied_changes,
                    skipped_repairs=skipped_repairs,
                    warnings=warnings,
                )
            if arrows:
                phase5_arrow_snaps = {
                    a["id"]: {
                        "points": deepcopy(a.get("points")),
                        "x": a.get("x"),
                        "y": a.get("y"),
                    }
                    for a in arrows
                    if a.get("id")
                }
                reroute_scene_arrows(active, clearance=15.0 * gap_mult, lane_spacing=24.0)
                for a in arrows:
                    aid = a.get("id")
                    if not aid or a.get("locked"):
                        continue
                    snap = phase5_arrow_snaps.get(aid, {})
                    if a.get("points") != snap.get("points") or a.get("x") != snap.get("x") or a.get("y") != snap.get("y"):
                        applied_changes.append(
                            {
                                "element_id": aid,
                                "change_type": "reroute",
                                "description": f"Recalculated obstacle-aware orthogonal path for connector '{aid}' after spacing adjustments.",
                                "before": {"points": snap.get("points"), "x": snap.get("x"), "y": snap.get("y")},
                                "after": {"points": a.get("points"), "x": a.get("x"), "y": a.get("y"), "elbowed": a.get("elbowed")},
                            }
                        )

    return elements, applied_changes, skipped_repairs, warnings


def auto_fix_scene_layout(
    document_or_elements: Any,
    dry_run: bool = False,
    repair_scope: str = "all",
    aggressiveness: str = "balanced",
    min_gap: float = 30.0,
) -> dict[str, Any]:
    """Analyze and systematically repair layout defects in an Excalidraw scene with transactional validation.

    dry_run executes all repair phases and A* routing on an isolated snapshot before discarding changes, costing the same compute as a real run.
    min_gap must be between 0 and 1000 (effective spacing defect threshold is min_gap * 0.65).
    aggressiveness='gentle' provides a smaller expansion (0.8x), not compaction.
    """
    scope, aggr, m_gap = _validate_params(repair_scope, aggressiveness, min_gap)
    active, is_doc = _extract_active_elements(document_or_elements)
    warnings: list[str] = []

    # Step 1: Snapshot original scene for clean diffs and guaranteed rollback
    snapshot_original = deepcopy(document_or_elements)

    # Step 2: Empty or trivial scene handling
    if not active:
        return {
            "status": "no_changes_needed",
            "dry_run": dry_run,
            "initial_issues": [],
            "final_issues": [],
            "fixed_issues_count": 0,
            "unresolved_issues": [],
            "planned_changes": [],
            "applied_changes": [],
            "changed_element_ids": [],
            "skipped_repairs": [],
            "warnings": _cap_warnings(["Scene contains no active elements to repair."]),
            "rolled_back": False,
            "document": snapshot_original if is_doc else {"type": "excalidraw", "version": 2, "elements": []},
        }

    # Step 3: Run comprehensive initial diagnostics
    initial_issues = diagnose_layout_issues(snapshot_original, min_gap=m_gap, aggressiveness=aggr, warnings=warnings)

    # Step 4: If scene is already valid and has no defects
    if not initial_issues:
        return {
            "status": "no_changes_needed",
            "dry_run": dry_run,
            "initial_issues": [],
            "final_issues": [],
            "fixed_issues_count": 0,
            "unresolved_issues": [],
            "planned_changes": [],
            "applied_changes": [],
            "changed_element_ids": [],
            "skipped_repairs": [],
            "warnings": _cap_warnings(warnings),
            "rolled_back": False,
            "document": snapshot_original if is_doc else {"type": "excalidraw", "version": 2, "elements": snapshot_original},
        }

    # Step 5: Build deterministic repair plan
    planned_changes = summarize_planned_repairs(
        snapshot_original,
        initial_issues,
        repair_scope=scope,
        aggressiveness=aggr,
        min_gap=m_gap,
    )

    # Step 6: Create draft and apply repairs
    draft = deepcopy(snapshot_original)
    repaired, applied_changes, skipped_repairs, warnings = apply_layout_repairs(
        draft,
        repair_scope=scope,
        aggressiveness=aggr,
        min_gap=m_gap,
    )

    # Step 7: Re-run diagnostics on post-repair geometry
    final_issues = diagnose_layout_issues(draft, min_gap=m_gap, aggressiveness=aggr, warnings=warnings)

    initial_severe_ids = _severe_ids(initial_issues)
    final_severe_ids = _severe_ids(final_issues)
    new_severe = final_severe_ids - initial_severe_ids

    # Step 8: Regression detection and rollback guarantee
    if new_severe:
        new_severe_str = ", ".join(sorted(new_severe))
        warnings.append(
            f"Layout repair aborted: regression detected (new severe defects introduced: {new_severe_str}). Rolled back to original state."
        )
        return {
            "status": "rolled_back",
            "dry_run": dry_run,
            "initial_issues": initial_issues,
            "final_issues": initial_issues,
            "fixed_issues_count": 0,
            "unresolved_issues": initial_issues,
            "planned_changes": planned_changes,
            "applied_changes": [],
            "changed_element_ids": [],
            "skipped_repairs": skipped_repairs,
            "warnings": _cap_warnings(warnings),
            "rolled_back": True,
            "document": snapshot_original if is_doc else {"type": "excalidraw", "version": 2, "elements": snapshot_original},
        }

    fixed_count = len(initial_severe_ids - final_severe_ids)
    changed_ids = list({c["element_id"] for c in applied_changes})

    # Step 9: Handle dry_run mode
    if dry_run:
        return {
            "status": "dry_run",
            "dry_run": True,
            "initial_issues": initial_issues,
            "final_issues": final_issues,
            "fixed_issues_count": fixed_count,
            "unresolved_issues": final_issues,
            "planned_changes": planned_changes,
            "applied_changes": applied_changes,
            "changed_element_ids": changed_ids,
            "skipped_repairs": skipped_repairs,
            "warnings": _cap_warnings(warnings),
            "rolled_back": False,
            "document": snapshot_original if is_doc else {"type": "excalidraw", "version": 2, "elements": snapshot_original},
        }

    # Step 10: Status classification
    scope_type_map = {
        "text": {"text_clipping"},
        "overlaps": {"shape_overlap"},
        "containment": {"frame_containment"},
        "connectors": {"connector_collision"},
        "spacing": {"crowded_spacing"},
    }
    target_issue_types = scope_type_map.get(scope) if scope != "all" else None
    if target_issue_types is not None:
        scoped_final_severe = {
            i["id"]
            for i in final_issues
            if i.get("severity") in ("critical", "warning") and i.get("type") in target_issue_types
        }
        scoped_skipped = [s for s in skipped_repairs if s.get("type") in target_issue_types]
    else:
        scoped_final_severe = final_severe_ids
        scoped_skipped = skipped_repairs

    final_severe = len(scoped_final_severe)
    if not applied_changes:
        status = "no_changes_needed"
    elif final_severe > 0 or (final_issues and scoped_skipped):
        status = "partially_repaired"
    elif applied_changes:
        status = "repaired"
    else:
        status = "no_changes_needed"

    if status == "repaired" and fixed_count == 0:
        fixed_count = max(1, len(initial_issues) - len(final_issues))

    return {
        "status": status,
        "dry_run": False,
        "initial_issues": initial_issues,
        "final_issues": final_issues,
        "fixed_issues_count": fixed_count,
        "unresolved_issues": final_issues,
        "planned_changes": planned_changes,
        "applied_changes": applied_changes,
        "changed_element_ids": changed_ids,
        "skipped_repairs": skipped_repairs,
        "warnings": _cap_warnings(warnings),
        "rolled_back": False,
        "document": draft if is_doc else {"type": "excalidraw", "version": 2, "elements": draft},
    }
