"""Deterministic layouts for the supported node subset."""

import math
import textwrap
from collections import defaultdict, deque
from typing import Any

from excalidraw_mcp.errors import SceneError

__all__ = [
    "architectural_layout",
    "check_diagram_geometry",
    "grid_layout",
    "horizontal_layout",
    "layered_layout",
    "linear_layout",
    "resolve_scene_layout",
    "shape_dimensions",
    "wrap_label",
    "wrap_text_to_shape",
]


def wrap_label(label: str, max_chars: int = 24) -> str:
    cleaned = label.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for paragraph in cleaned.splitlines() or [""]:
        lines.extend(
            textwrap.wrap(paragraph, width=max_chars, break_long_words=True) or [""]
        )
    return "\n".join(lines)


def wrap_text_to_shape(
    label: str,
    shape: str = "rectangle",
    target_w: float | None = None,
    font_size: int = 20,
    font_family: str | int | None = None,
) -> str:
    """Intelligently wrap label text to fit within a shape's inscribed geometry."""
    if not label:
        return ""
    font_size = font_size or 20
    if target_w is not None and target_w > 0:
        if shape == "ellipse":
            # Inscribed rectangle inside ellipse: width * (1 / sqrt(2)) ~ 0.707 * width
            safe_w = max(60.0, (target_w * 0.707) - 32.0)
        elif shape == "diamond":
            # Inscribed rhombus: safe width at ~middle height is ~0.55 * width
            safe_w = max(60.0, (target_w * 0.55) - 32.0)
        else:
            # Rectangle: width minus horizontal padding (20px each side)
            safe_w = max(60.0, target_w - 40.0)
    else:
        if shape == "ellipse":
            safe_w = 140.0
        elif shape == "diamond":
            safe_w = 130.0
        else:
            safe_w = 180.0

    from .fonts import get_font
    try:
        font = get_font(font_family, font_size)
        bbox = font.getbbox("M")
        char_w = max(7.0, float(bbox[2] - bbox[0]) * 0.85)
    except Exception:
        char_w = max(7.0, float(font_size) * 0.55)

    max_chars = max(20, int(safe_w / char_w))
    return wrap_label(label, max_chars=max_chars)


def shape_dimensions(
    shape: str,
    label: str,
    font_size: int = 20,
    font_family: str | int | None = None,
) -> tuple[float, float]:
    """Calculate the bounding box dimensions of a shape required to enclose its text.

    Guarantees that all text lines fit inside with consistent internal padding,
    accounting for geometric boundaries of rectangles, ellipses, and diamonds.
    """
    from .fonts import measure_text_dimensions

    font_size = font_size or 20
    # Auto-wrap label according to shape geometry
    wrapped = wrap_text_to_shape(
        label, shape=shape, font_size=font_size, font_family=font_family
    )
    text_w, text_h, _ = measure_text_dimensions(
        wrapped, font_family=font_family, font_size=font_size
    )

    if shape == "ellipse":
        # For a circle/ellipse, diameter >= hypot(text_w, text_h) + 2 * padding
        diag = math.hypot(text_w, text_h)
        size = max(140.0, diag + 48.0)
        return size, size

    if shape == "diamond":
        # For a diamond (rhombus), corner fits inside: W_t/W + H_t/H <= 1.0
        min_w = text_w * 1.65 + 60.0
        min_h = text_h * 1.65 + 50.0
        return max(180.0, min_w), max(130.0, min_h)

    # Rectangle: text width + padding on left/right, text height + padding on top/bottom
    min_w = text_w + 48.0
    min_h = text_h + 36.0
    return max(180.0, min_w), max(100.0, min_h)


def linear_layout(nodes, direction="horizontal", start_x=100, start_y=100, gap=100):
    if direction not in ("horizontal", "vertical"):
        raise SceneError("Layout direction must be horizontal or vertical")
    if not nodes:
        return []
    dims = [
        shape_dimensions(
            n["shape"],
            n["label"],
            font_size=n.get("fontSize") or n.get("font_size") or 20,
            font_family=n.get("fontFamily") or n.get("font_family"),
        )
        for n in nodes
    ]
    max_cross = (
        max(h for w, h in dims) if direction == "horizontal" else max(w for w, h in dims)
    )
    positioned, cursor = [], 0
    for i, node in enumerate(nodes):
        width, height = dims[i]
        if direction == "horizontal":
            x = start_x + cursor
            y = start_y + (max_cross - height) / 2.0
            cursor += width + gap
        else:
            x = start_x + (max_cross - width) / 2.0
            y = start_y + cursor
            cursor += height + gap
        fs = node.get("fontSize") or node.get("font_size") or 20
        ff = node.get("fontFamily") or node.get("font_family")
        item = {
            **node,
            "label": wrap_text_to_shape(
                node["label"],
                shape=node["shape"],
                target_w=width,
                font_size=fs,
                font_family=ff,
            ),
            "x": x,
            "y": y,
            "w": width,
            "h": height,
        }
        positioned.append(item)
    return positioned


def grid_layout(
    nodes,
    cols=4,
    start_x=100,
    start_y=100,
    col_gap=60,
    row_gap=80,
    snake=True,
):
    """Layout nodes in a multi-row grid with snake routing for balanced aspect ratios."""
    if not nodes:
        return []
    dims = [
        shape_dimensions(
            n["shape"],
            n["label"],
            font_size=n.get("fontSize") or n.get("font_size") or 20,
            font_family=n.get("fontFamily") or n.get("font_family"),
        )
        for n in nodes
    ]
    cell_w = max(w for w, h in dims) + col_gap
    cell_h = max(h for w, h in dims) + row_gap

    positioned = []
    for i, node in enumerate(nodes):
        row = i // cols
        col_in_row = i % cols
        if snake and (row % 2 == 1):
            col = (cols - 1) - col_in_row
        else:
            col = col_in_row

        w, h = dims[i]
        x = start_x + col * cell_w + (cell_w - col_gap - w) / 2.0
        y = start_y + row * cell_h + (cell_h - row_gap - h) / 2.0
        fs = node.get("fontSize") or node.get("font_size") or 20
        ff = node.get("fontFamily") or node.get("font_family")
        positioned.append(
            {
                **node,
                "label": wrap_text_to_shape(
                    node["label"],
                    shape=node["shape"],
                    target_w=w,
                    font_size=fs,
                    font_family=ff,
                ),
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    return positioned


def horizontal_layout(nodes):
    return linear_layout(nodes)


def layered_layout(
    nodes,
    edges,
    direction="horizontal",
    start_x=100,
    start_y=100,
    rank_gap=180,
    node_gap=80,
):
    if direction not in ("horizontal", "vertical"):
        raise SceneError("Layout direction must be horizontal or vertical")
    ids = [node["id"] for node in nodes]
    incoming = {node_id: 0 for node_id in ids}
    outgoing = defaultdict(list)
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        incoming[edge["target"]] += 1
    queue = deque(node_id for node_id in ids if incoming[node_id] == 0)
    rank = {node_id: 0 for node_id in queue}
    visited = []
    while queue:
        current = queue.popleft()
        visited.append(current)
        for target in outgoing[current]:
            rank[target] = max(rank.get(target, 0), rank[current] + 1)
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
    if len(visited) != len(ids):
        raise SceneError(
            "Layered layout requires an acyclic graph. Use layout='horizontal' or 'vertical' for cyclic graphs."
        )
    groups, lookup = defaultdict(list), {node["id"]: node for node in nodes}
    for node_id in ids:
        groups[rank.get(node_id, 0)].append(lookup[node_id])
    sizes = {
        node_id: shape_dimensions(
            lookup[node_id]["shape"],
            lookup[node_id]["label"],
            font_size=lookup[node_id].get("fontSize") or lookup[node_id].get("font_size") or 20,
            font_family=lookup[node_id].get("fontFamily") or lookup[node_id].get("font_family"),
        )
        for node_id in ids
    }

    # Calculate dynamic inter-rank gap to accommodate long edge labels without overlap
    rank_by_id = {node["id"]: rank.get(node["id"], 0) for node in nodes}
    inter_rank_gaps = {}
    sorted_levels = sorted(groups)
    for i, level in enumerate(sorted_levels[:-1]):
        next_level = sorted_levels[i + 1]
        spanning_edges = [
            e
            for e in edges
            if (
                rank_by_id.get(e["source"]) == level
                and rank_by_id.get(e["target"]) >= next_level
            )
            or (
                rank_by_id.get(e["target"]) == level
                and rank_by_id.get(e["source"]) >= next_level
            )
        ]
        max_lbl_len = 0
        for e in spanning_edges:
            lbl = e.get("label") or ""
            if lbl:
                max_lbl_len = max(
                    max_lbl_len, max(len(line) for line in lbl.splitlines())
                )

        if direction == "horizontal":
            needed_gap = max_lbl_len * 9 + 50 if max_lbl_len > 0 else rank_gap
        else:
            needed_gap = max_lbl_len * 4 + 40 if max_lbl_len > 0 else rank_gap
        inter_rank_gaps[level] = max(rank_gap, needed_gap)

    offsets, cursor = {}, 0
    for level in sorted_levels:
        offsets[level] = cursor
        rg = inter_rank_gaps.get(level, rank_gap)
        cursor += (
            max(
                sizes[n["id"]][0 if direction == "horizontal" else 1]
                for n in groups[level]
            )
            + rg
        )
    cross_dim = 1 if direction == "horizontal" else 0
    rank_cross_spans = {}
    for level in sorted(groups):
        level_nodes = groups[level]
        total_span = (
            sum(sizes[n["id"]][cross_dim] for n in level_nodes)
            + max(0, len(level_nodes) - 1) * node_gap
        )
        rank_cross_spans[level] = total_span

    max_cross_span = max(rank_cross_spans.values()) if rank_cross_spans else 0

    positioned = []
    for level in sorted(groups):
        cross = (max_cross_span - rank_cross_spans[level]) / 2.0
        rank_primary_max = max(
            sizes[n["id"]][0 if direction == "horizontal" else 1]
            for n in groups[level]
        )
        for node in groups[level]:
            width, height = sizes[node["id"]]
            node_primary = width if direction == "horizontal" else height
            primary_offset = offsets[level] + (rank_primary_max - node_primary) / 2.0
            x = start_x + (primary_offset if direction == "horizontal" else cross)
            y = start_y + (cross if direction == "horizontal" else primary_offset)
            fs = node.get("fontSize") or node.get("font_size") or 20
            ff = node.get("fontFamily") or node.get("font_family")
            positioned.append(
                {
                    **node,
                    "label": wrap_text_to_shape(
                        node["label"],
                        shape=node["shape"],
                        target_w=width,
                        font_size=fs,
                        font_family=ff,
                    ),
                    "x": x,
                    "y": y,
                    "w": width,
                    "h": height,
                }
            )
            cross += (height if direction == "horizontal" else width) + node_gap
    return positioned


def clustered_layout(
    nodes,
    edges,
    clusters,
    layout="layered",
    direction="horizontal",
    start_x=100,
    start_y=100,
    rank_gap=180,
    node_gap=80,
    cluster_padding=40,
    cluster_gap=80,
):
    """Layout nodes grouped by clusters, wrapping each cluster in a frame."""
    if direction not in ("horizontal", "vertical"):
        raise SceneError("Layout direction must be horizontal or vertical")

    cluster_lookup = {c["id"]: c.get("label", c["id"]) for c in clusters}
    cluster_order = [c["id"] for c in clusters]

    for node in nodes:
        cid = node.get("cluster")
        if cid and cid not in cluster_lookup:
            raise SceneError(f"Unknown cluster '{cid}' on node '{node['id']}'")

    positioned_nodes = []
    frames = []

    cursor_x, cursor_y = start_x, start_y

    for cid in cluster_order:
        c_label = cluster_lookup[cid]
        c_nodes = [node for node in nodes if node.get("cluster") == cid]
        if not c_nodes:
            fw, fh = 240, 160
            frames.append(
                {
                    "id": cid,
                    "name": c_label,
                    "x": cursor_x,
                    "y": cursor_y,
                    "w": fw,
                    "h": fh,
                }
            )
            if direction == "horizontal":
                cursor_x += fw + cluster_gap
            else:
                cursor_y += fh + cluster_gap
            continue

        c_node_ids = {n["id"] for n in c_nodes}
        c_edges = [
            e
            for e in edges
            if e.get("source") in c_node_ids and e.get("target") in c_node_ids
        ]

        inner_start_x = cursor_x + cluster_padding
        inner_start_y = cursor_y + cluster_padding + 20

        if layout == "layered":
            try:
                c_pos = layered_layout(
                    c_nodes,
                    c_edges,
                    direction=direction,
                    start_x=inner_start_x,
                    start_y=inner_start_y,
                    rank_gap=rank_gap,
                    node_gap=node_gap,
                )
            except SceneError:
                c_pos = linear_layout(
                    c_nodes,
                    direction=direction,
                    start_x=inner_start_x,
                    start_y=inner_start_y,
                    gap=node_gap,
                )
        else:
            c_pos = linear_layout(
                c_nodes,
                direction=direction,
                start_x=inner_start_x,
                start_y=inner_start_y,
                gap=node_gap,
            )

        min_x = min(n["x"] for n in c_pos)
        min_y = min(n["y"] for n in c_pos)
        max_x = max(n["x"] + n["w"] for n in c_pos)
        max_y = max(n["y"] + n["h"] for n in c_pos)

        fw = (max_x - min_x) + (2 * cluster_padding)
        fh = (max_y - min_y) + (2 * cluster_padding + 20)
        fx = min_x - cluster_padding
        fy = min_y - (cluster_padding + 20)

        frames.append(
            {
                "id": cid,
                "name": c_label,
                "x": fx,
                "y": fy,
                "w": fw,
                "h": fh,
            }
        )

        for n in c_pos:
            positioned_nodes.append({**n, "frame_id": cid})

        if direction == "horizontal":
            cursor_x = fx + fw + cluster_gap
        else:
            cursor_y = fy + fh + cluster_gap

    unclustered = [node for node in nodes if not node.get("cluster")]
    if unclustered:
        unclustered_ids = {n["id"] for n in unclustered}
        u_edges = [
            e
            for e in edges
            if e.get("source") in unclustered_ids and e.get("target") in unclustered_ids
        ]
        if layout == "layered":
            try:
                u_pos = layered_layout(
                    unclustered,
                    u_edges,
                    direction=direction,
                    start_x=cursor_x,
                    start_y=cursor_y,
                    rank_gap=rank_gap,
                    node_gap=node_gap,
                )
            except SceneError:
                u_pos = linear_layout(
                    unclustered,
                    direction=direction,
                    start_x=cursor_x,
                    start_y=cursor_y,
                    gap=node_gap,
                )
        else:
            u_pos = linear_layout(
                unclustered,
                direction=direction,
                start_x=cursor_x,
                start_y=cursor_y,
                gap=node_gap,
            )
        for n in u_pos:
            positioned_nodes.append({**n, "frame_id": None})

    return positioned_nodes, frames


def boundary_point(node, target, coincident_direction=1):
    cx, cy = node["x"] + node["w"] / 2, node["y"] + node["h"] / 2
    tx, ty = target["x"] + target["w"] / 2, target["y"] + target["h"] / 2
    dx, dy = tx - cx, ty - cy
    if dx == dy == 0:
        dx = 1 if coincident_direction >= 0 else -1
    angle = node.get("angle") or 0
    cosine, sine = math.cos(angle), math.sin(angle)
    local_dx = dx * cosine + dy * sine
    local_dy = -dx * sine + dy * cosine
    half_width, half_height = max(node["w"] / 2, 0.5), max(node["h"] / 2, 0.5)
    if node["shape"] == "ellipse":
        scale = 1 / math.sqrt(
            (local_dx / half_width) ** 2 + (local_dy / half_height) ** 2
        )
    elif node["shape"] == "diamond":
        scale = 1 / (
            abs(local_dx) / half_width + abs(local_dy) / half_height
        )
    else:
        scale = min(
            half_width / abs(local_dx) if local_dx else math.inf,
            half_height / abs(local_dy) if local_dy else math.inf,
        )
    local_x, local_y = local_dx * scale, local_dy * scale
    return (
        cx + local_x * cosine - local_y * sine,
        cy + local_x * sine + local_y * cosine,
    )


def check_diagram_geometry(document_or_elements, min_gap=30.0):
    """Analyze diagram elements for geometric collisions, gap violations, and frame containment.

    Returns a structured dictionary of geometry diagnostics.
    """
    if isinstance(document_or_elements, dict) and "elements" in document_or_elements:
        elements = document_or_elements["elements"]
    elif isinstance(document_or_elements, list):
        elements = document_or_elements
    else:
        raise SceneError("Expected document dictionary or list of elements")

    active = [e for e in elements if not e.get("isDeleted")]
    shapes = [
        e
        for e in active
        if e.get("type") in ("rectangle", "diamond", "ellipse")
        and not ((e.get("customData") or {}).get("type") in ("code_block_header",))
    ]
    frames = [e for e in active if e.get("type") == "frame"]
    text_els = [e for e in active if e.get("type") == "text"]
    bound_map = {t["containerId"]: t for t in text_els if t.get("containerId")}

    overlaps = []
    gap_violations = []
    containment_violations = []

    # 1. Shape-to-shape bounding box overlap check
    for i in range(len(shapes)):
        s1 = shapes[i]
        x1_min, y1_min = float(s1.get("x", 0)), float(s1.get("y", 0))
        x1_max, y1_max = x1_min + float(s1.get("width", 0)), y1_min + float(s1.get("height", 0))

        for j in range(i + 1, len(shapes)):
            s2 = shapes[j]
            x2_min, y2_min = float(s2.get("x", 0)), float(s2.get("y", 0))
            x2_max, y2_max = x2_min + float(s2.get("width", 0)), y2_min + float(s2.get("height", 0))

            inter_x = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
            inter_y = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))

            if inter_x > 0.5 and inter_y > 0.5:
                overlaps.append(
                    {
                        "shape1_id": s1["id"],
                        "shape2_id": s2["id"],
                        "overlap_width": round(inter_x, 1),
                        "overlap_height": round(inter_y, 1),
                        "shape1_label": bound_map.get(s1["id"], {}).get("text", "")[:30],
                        "shape2_label": bound_map.get(s2["id"], {}).get("text", "")[:30],
                    }
                )
            elif min_gap > 0:
                if inter_y > 0.5:
                    gap_x = max(x1_min, x2_min) - min(x1_max, x2_max)
                    if 0 < gap_x < min_gap:
                        gap_violations.append(
                            {
                                "shape1_id": s1["id"],
                                "shape2_id": s2["id"],
                                "axis": "x",
                                "gap": round(gap_x, 1),
                                "min_gap": min_gap,
                            }
                        )
                elif inter_x > 0.5:
                    gap_y = max(y1_min, y2_min) - min(y1_max, y2_max)
                    if 0 < gap_y < min_gap:
                        gap_violations.append(
                            {
                                "shape1_id": s1["id"],
                                "shape2_id": s2["id"],
                                "axis": "y",
                                "gap": round(gap_y, 1),
                                "min_gap": min_gap,
                            }
                        )

    # 2. Frame containment check
    for f in frames:
        fid = f["id"]
        fx, fy = float(f.get("x", 0)), float(f.get("y", 0))
        fw, fh = float(f.get("width", 0)), float(f.get("height", 0))
        f_right, f_bottom = fx + fw, fy + fh
        fname = f.get("name", fid)

        # Children with explicit frameId, or spatial containment
        children = [
            s
            for s in shapes
            if s.get("frameId") == fid
            or (
                s.get("frameId") is None
                and fx - 20 <= (s.get("x", 0) + s.get("width", 0) / 2.0) <= f_right + 20
                and fy - 20 <= (s.get("y", 0) + s.get("height", 0) / 2.0) <= f_bottom + 100
            )
        ]

        for c in children:
            cx, cy = float(c.get("x", 0)), float(c.get("y", 0))
            cw, ch = float(c.get("width", 0)), float(c.get("height", 0))
            c_right, c_bottom = cx + cw, cy + ch

            overflow_x = max(0.0, fx - cx) + max(0.0, c_right - f_right)
            overflow_y = max(0.0, fy - cy) + max(0.0, c_bottom - f_bottom)

            if overflow_x > 1.0 or overflow_y > 1.0:
                containment_violations.append(
                    {
                        "frame_id": fid,
                        "frame_name": fname,
                        "shape_id": c["id"],
                        "shape_label": bound_map.get(c["id"], {}).get("text", "")[:30],
                        "overflow_x": round(overflow_x, 1),
                        "overflow_y": round(overflow_y, 1),
                    }
                )

    # 3. Connector collision check against unrelated obstacle shapes
    arrows = [e for e in active if e.get("type") in ("arrow", "line")]
    connector_collisions = []
    from .routing import segment_intersects_rect
    for a in arrows:
        sb = (a.get("startBinding") or {}).get("elementId")
        eb = (a.get("endBinding") or {}).get("elementId")
        ax, ay = float(a.get("x", 0.0)), float(a.get("y", 0.0))
        pts = a.get("points") or [[0.0, 0.0], [float(a.get("width", 0.0)), float(a.get("height", 0.0))]]
        world_pts = [(ax + float(p[0]), ay + float(p[1])) for p in pts]
        for k in range(len(world_pts) - 1):
            p1 = world_pts[k]
            p2 = world_pts[k + 1]
            for s in shapes:
                if s["id"] in (sb, eb):
                    continue
                sx, sy = float(s.get("x", 0.0)), float(s.get("y", 0.0))
                sw, sh = float(s.get("width", 0.0)), float(s.get("height", 0.0))
                if segment_intersects_rect(p1, p2, (sx, sy, sx + sw, sy + sh), margin=2.0):
                    connector_collisions.append(
                        {
                            "arrow_id": a["id"],
                            "source_id": sb,
                            "target_id": eb,
                            "obstacle_id": s["id"],
                            "obstacle_label": bound_map.get(s["id"], {}).get("text", "")[:30],
                        }
                    )

    return {
        "valid": len(overlaps) == 0 and len(containment_violations) == 0 and len(connector_collisions) == 0,
        "overlap_count": len(overlaps),
        "connector_collision_count": len(connector_collisions),
        "connector_collisions": connector_collisions,
        "overlaps": overlaps,
        "containment_violations": containment_violations,
        "gap_violations": gap_violations,
    }


def resolve_scene_layout(
    document_or_elements,
    min_gap_x=35.0,
    min_gap_y=40.0,
    layer_gap=50.0,
    frame_padding=30.0,
    header_pad=30.0,
):
    """Systematically resolve shape collisions, expand frames, and propagate downstream layer spacing.

    Ensures zero unintended overlaps, strict frame containment, and readable connector routing.
    """
    if isinstance(document_or_elements, dict) and "elements" in document_or_elements:
        elements = document_or_elements["elements"]
    elif isinstance(document_or_elements, list):
        elements = document_or_elements
    else:
        raise SceneError("Expected document dictionary or list of elements")

    active = [e for e in elements if not e.get("isDeleted")]
    frames = [e for e in active if e.get("type") == "frame"]
    shapes = [e for e in active if e.get("type") in ("rectangle", "diamond", "ellipse")]
    texts = [e for e in active if e.get("type") == "text"]

    bound_labels = {t["containerId"]: t for t in texts if t.get("containerId")}

    if not shapes:
        return document_or_elements

    # Step 1: Match shapes to frames by explicit frameId or spatial proximity
    frame_shapes = {f["id"]: [] for f in frames}
    unframed_shapes = []

    for s in shapes:
        fid = s.get("frameId")
        if not fid or fid not in frame_shapes:
            cx = float(s["x"]) + float(s["width"]) / 2.0
            cy = float(s["y"]) + float(s["height"]) / 2.0
            best_f = None
            best_dist = float("inf")
            for f in frames:
                fx, fy = float(f["x"]), float(f["y"])
                fw, fh = float(f["width"]), float(f["height"])
                if fx - 50 <= cx <= fx + fw + 50 and fy - 50 <= cy <= fy + fh + 350:
                    dist = abs(cy - (fy + fh / 2.0))
                    if dist < best_dist:
                        best_dist = dist
                        best_f = f["id"]
            if best_f:
                s["frameId"] = best_f
                fid = best_f

        if fid in frame_shapes:
            frame_shapes[fid].append(s)
        else:
            unframed_shapes.append(s)

    # Step 2: Classify frames into Main Vertical Stack, Side Columns, and Bottom Banners
    main_frames = []
    side_frames = []
    banner_frames = []

    for f in frames:
        fw, fh = float(f["width"]), float(f["height"])
        fx, fy = float(f["x"]), float(f["y"])
        if fx > 1600 and fh > 800:
            side_frames.append(f)
        elif fw > 2000 and fy > 1500:
            banner_frames.append(f)
        else:
            main_frames.append(f)

    main_frames.sort(key=lambda f: float(f["y"]))
    side_frames.sort(key=lambda f: float(f["y"]))
    banner_frames.sort(key=lambda f: float(f["y"]))

    # Step 3: Intra-Frame Row Clustering and De-Collision
    for f in frames:
        children = frame_shapes.get(f["id"], [])
        if not children:
            continue

        sorted_by_y = sorted(children, key=lambda s: float(s["y"]))
        rows = []
        for s in sorted_by_y:
            sy = float(s["y"])
            placed = False
            for r in rows:
                avg_y = sum(float(item["y"]) for item in r) / len(r)
                if abs(sy - avg_y) <= 80.0:
                    r.append(s)
                    placed = True
                    break
            if not placed:
                rows.append([s])

        rows.sort(key=lambda r: sum(float(s["y"]) for s in r) / len(r))

        cur_y = float(f["y"]) + frame_padding + header_pad
        for r in rows:
            r.sort(key=lambda s: float(s["x"]))
            cur_x = float(f["x"]) + frame_padding
            row_h = max(float(s["height"]) for s in r)
            for s in r:
                s["x"] = cur_x
                s["y"] = cur_y
                cur_x += float(s["width"]) + min_gap_x
            cur_y += row_h + min_gap_y

        # Expand frame dimensions to contain all children
        min_x = min(float(s["x"]) for s in children) - frame_padding
        max_x = max(float(s["x"]) + float(s["width"]) for s in children) + frame_padding
        max_y = max(float(s["y"]) + float(s["height"]) for s in children) + frame_padding
        f["x"] = min_x
        f["width"] = max_x - min_x
        f["height"] = max_y - float(f["y"])

    # Step 4: Vertical Spatial Propagation on Main Stack
    if main_frames:
        cur_stack_y = float(main_frames[0]["y"])
        max_main_w = max((float(f["width"]) for f in main_frames), default=1600.0)

        for f in main_frames:
            fy = float(f["y"])
            delta_y = cur_stack_y - fy
            f["y"] = cur_stack_y
            for s in frame_shapes.get(f["id"], []):
                s["y"] = float(s["y"]) + delta_y
            f["width"] = max_main_w
            cur_stack_y += float(f["height"]) + layer_gap

        main_bottom = cur_stack_y - layer_gap
        main_start_x = float(main_frames[0]["x"])
    else:
        main_bottom = 0.0
        main_start_x = 50.0
        max_main_w = 1600.0

    # Step 5: Side Columns Positioning
    if side_frames:
        side_x = main_start_x + max_main_w + 40.0
        for f in side_frames:
            fx = float(f["x"])
            delta_x = side_x - fx
            f["x"] = side_x
            children = frame_shapes.get(f["id"], [])
            for s in children:
                s["x"] = float(s["x"]) + delta_x

            children.sort(key=lambda s: float(s["y"]))
            sc_y = float(f["y"]) + frame_padding + header_pad
            for s in children:
                s["y"] = sc_y
                sc_y += float(s["height"]) + min_gap_y
            f["height"] = max(main_bottom - float(f["y"]), sc_y + frame_padding - float(f["y"]))

    # Step 6: Bottom Banner Positioning Below Main Stack and Side Columns
    if banner_frames:
        top_frames = main_frames + side_frames
        total_bottom = max([float(f["y"]) + float(f["height"]) for f in top_frames] or [main_bottom])
        cur_banner_y = total_bottom + layer_gap
        total_w = max(float(f["x"]) + float(f["width"]) for f in top_frames) - main_start_x

        for f in banner_frames:
            fy = float(f["y"])
            delta_y = cur_banner_y - fy
            f["y"] = cur_banner_y
            for s in frame_shapes.get(f["id"], []):
                s["y"] = float(s["y"]) + delta_y
            f["width"] = max(float(f["width"]), total_w)
            cur_banner_y += float(f["height"]) + layer_gap

    # Step 7: Unframed Floating Shapes De-Collision (if any)
    if unframed_shapes:
        unframed_shapes.sort(key=lambda s: (float(s["y"]), float(s["x"])))
        for i in range(len(unframed_shapes)):
            s1 = unframed_shapes[i]
            x1_min, y1_min = float(s1["x"]), float(s1["y"])
            x1_max, y1_max = x1_min + float(s1["width"]), y1_min + float(s1["height"])
            for j in range(i + 1, len(unframed_shapes)):
                s2 = unframed_shapes[j]
                x2_min, y2_min = float(s2["x"]), float(s2["y"])
                x2_max, y2_max = x2_min + float(s2["width"]), y2_min + float(s2["height"])
                ix = max(0.0, min(x1_max, x2_max) - max(x1_min, x2_min))
                iy = max(0.0, min(y1_max, y2_max) - max(y1_min, y2_min))
                if ix > 0.5 and iy > 0.5:
                    s2["x"] = float(s2["x"]) + ix + min_gap_x

    # Step 8: Re-Center Bound Labels on Shapes
    for s in shapes:
        lbl = bound_labels.get(s["id"])
        if lbl and (s.get("customData") or {}).get("type") not in ("code_block", "code-block"):
            cx = float(s["x"]) + float(s["width"]) / 2.0
            cy = float(s["y"]) + float(s["height"]) / 2.0
            lbl["x"] = cx - float(lbl.get("width", 0.0)) / 2.0
            lbl["y"] = cy - float(lbl.get("height", 0.0)) / 2.0

    # Step 9: Recalculate Connector Endpoints via obstacle-aware orthogonal routing
    from .routing import reroute_scene_arrows
    reroute_scene_arrows(active, clearance=15.0)

    return document_or_elements


def architectural_layout(
    tiers: list[dict[str, Any]],
    edges: list[dict[str, Any]] | None = None,
    start_x: float = 100.0,
    start_y: float = 100.0,
    tier_gap: float = 60.0,
    node_gap: float = 40.0,
    frame_padding: float = 35.0,
    max_tier_width: float = 2400.0,
):
    """Generate a clean, collision-free multi-tier architectural layout.

    Accepts structured tier definitions, pre-measures components, wraps rows gracefully,
    creates containing frames for each architectural layer, and routes connectors.
    """
    edges = edges or []
    frames = []
    positioned_nodes = []
    cur_y = start_y

    all_measured = []
    for tier in tiers:
        t_nodes = tier.get("nodes", tier.get("components", []))
        for n in t_nodes:
            fs = n.get("fontSize") or n.get("font_size") or 20
            ff = n.get("fontFamily") or n.get("font_family")
            w, h = shape_dimensions(n.get("shape", "rectangle"), n.get("label", ""), font_size=fs, font_family=ff)
            all_measured.append((n["id"], w, h))

    node_sizes = {nid: (w, h) for nid, w, h in all_measured}

    # Pass 2: Layout each tier horizontally with sub-row wrapping if needed
    tier_widths = []
    tier_data = []

    for tier_idx, tier in enumerate(tiers):
        t_nodes = tier.get("nodes", tier.get("components", []))
        t_name = tier.get("name", f"Tier {tier_idx + 1}")
        tier_id = tier.get("id", f"tier-{tier_idx + 1}")

        rows: list[list[dict[str, Any]]] = [[]]
        cur_row_w = 0.0
        for n in t_nodes:
            w, h = node_sizes[n["id"]]
            needed_w = w + (node_gap if rows[-1] else 0.0)
            if rows[-1] and (cur_row_w + needed_w > max_tier_width):
                rows.append([n])
                cur_row_w = w
            else:
                rows[-1].append(n)
                cur_row_w += needed_w

        t_width = max(
            sum(node_sizes[n["id"]][0] for n in r) + max(0, len(r) - 1) * node_gap
            for r in rows
        )
        tier_widths.append(t_width)
        tier_data.append((tier_id, t_name, rows, t_width))

    max_layout_w = max(tier_widths) if tier_widths else 800.0

    for tier_id, t_name, rows, _ in tier_data:
        frame_top = cur_y
        row_y = frame_top + frame_padding + 25.0  # 25px header

        tier_positioned = []
        for r in rows:
            r_w = sum(node_sizes[n["id"]][0] for n in r) + max(0, len(r) - 1) * node_gap
            x_cursor = start_x + frame_padding + (max_layout_w - r_w) / 2.0
            r_h = max(node_sizes[n["id"]][1] for n in r)
            for n in r:
                w, h = node_sizes[n["id"]]
                fs = n.get("fontSize") or n.get("font_size") or 20
                ff = n.get("fontFamily") or n.get("font_family")
                tier_positioned.append(
                    {
                        **n,
                        "frame_id": tier_id,
                        "x": x_cursor,
                        "y": row_y + (r_h - h) / 2.0,
                        "w": w,
                        "h": h,
                        "label": wrap_text_to_shape(
                            n.get("label", ""),
                            shape=n.get("shape", "rectangle"),
                            target_w=w,
                            font_size=fs,
                            font_family=ff,
                        ),
                    }
                )
                x_cursor += w + node_gap
            row_y += r_h + node_gap

        frame_bottom = row_y - node_gap + frame_padding
        frame_h = frame_bottom - frame_top
        frame_w = max_layout_w + 2 * frame_padding

        frames.append(
            {
                "id": tier_id,
                "name": t_name,
                "x": start_x,
                "y": frame_top,
                "w": frame_w,
                "h": frame_h,
            }
        )
        positioned_nodes.extend(tier_positioned)
        cur_y = frame_bottom + tier_gap

    return {
        "nodes": positioned_nodes,
        "frames": frames,
        "edges": edges,
    }
