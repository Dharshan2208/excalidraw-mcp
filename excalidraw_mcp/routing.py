"""Obstacle-aware orthogonal connector routing and label positioning.

Provides Manhattan A* routing around diagram components, frame-aware corridors,
multiple-edge offset handling, and collision-free connector label placement.
"""

from dataclasses import dataclass, field
import heapq
import math
from typing import Dict, List, Optional, Tuple

from .errors import SceneError

VALID_ROUTING_MODES = ("auto", "straight", "orthogonal", "curved")
FRAME_HEADER_HEIGHT = 28.0


def resolve_arrow_routing_mode(arrow_el: dict, default: str = "auto") -> str:
    """Resolve effective routing mode for an arrow from customData, elbowed, and roundness."""
    cd_mode = (arrow_el.get("customData") or {}).get("routing_mode")
    if cd_mode in VALID_ROUTING_MODES:
        return str(cd_mode)
    if arrow_el.get("elbowed"):
        return "orthogonal"
    pts = arrow_el.get("points") or []
    roundness = arrow_el.get("roundness")
    if isinstance(roundness, dict) and roundness.get("type") == 2 and len(pts) >= 3:
        return "curved"
    return default


def set_arrow_routing_mode(arrow_el: dict, mode: str) -> None:
    """Persist routing_mode in customData while preserving other customData fields."""
    if mode not in VALID_ROUTING_MODES:
        raise SceneError(f"Unsupported routing_mode: '{mode}'")
    cd = dict(arrow_el.get("customData") or {})
    cd["routing_mode"] = mode
    arrow_el["customData"] = cd


@dataclass
class SceneRoutingContext:
    """Snapshot of scene geometry used for scene-aware connector routing."""

    shapes: List[dict]
    shape_boxes: Dict[str, Tuple[float, float, float, float]]
    frames: List[dict]
    frame_headers: List[Tuple[float, float, float, float]]
    existing_segments: Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]]
    label_boxes: List[Tuple[float, float, float, float, Optional[str]]]
    density: float
    structure: str
    port_usage: Dict[Tuple[str, str], List[str]] = field(default_factory=dict)


def _arrow_world_segments(arrow_el: dict) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    ax = float(arrow_el.get("x", 0.0))
    ay = float(arrow_el.get("y", 0.0))
    pts = arrow_el.get("points") or [
        [0.0, 0.0],
        [float(arrow_el.get("width", 0.0)), float(arrow_el.get("height", 0.0))],
    ]
    wpts = [(ax + float(p[0]), ay + float(p[1])) for p in pts]
    return [(wpts[i], wpts[i + 1]) for i in range(len(wpts) - 1)]


def _classify_scene_structure(
    shapes: List[dict], frames: List[dict], arrows: List[dict]
) -> Tuple[str, float]:
    if not shapes:
        return "freeform", 0.0

    min_x = min(float(s.get("x", 0.0)) for s in shapes)
    min_y = min(float(s.get("y", 0.0)) for s in shapes)
    max_x = max(float(s.get("x", 0.0)) + float(s.get("width", s.get("w", 0.0))) for s in shapes)
    max_y = max(float(s.get("y", 0.0)) + float(s.get("height", s.get("h", 0.0))) for s in shapes)
    span_x = max(1.0, max_x - min_x)
    span_y = max(1.0, max_y - min_y)
    shape_area = sum(
        max(0.0, float(s.get("width", s.get("w", 0.0))))
        * max(0.0, float(s.get("height", s.get("h", 0.0))))
        for s in shapes
    )
    density = min(1.0, shape_area / max(1.0, span_x * span_y))

    if frames:
        framed = sum(1 for s in shapes if s.get("frameId"))
        if framed / len(shapes) >= 0.5:
            return "clustered", density

    # Degree check for sequential pipelines
    deg: Dict[str, int] = {str(s.get("id")): 0 for s in shapes if s.get("id")}
    shape_map = {str(s.get("id")): s for s in shapes if s.get("id")}
    directed_pairs: List[Tuple[dict, dict]] = []
    for a in arrows:
        sb = (a.get("startBinding") or {}).get("elementId")
        eb = (a.get("endBinding") or {}).get("elementId")
        if sb in shape_map and eb in shape_map:
            deg[sb] = deg.get(sb, 0) + 1
            deg[eb] = deg.get(eb, 0) + 1
            directed_pairs.append((shape_map[sb], shape_map[eb]))

    max_deg = max(deg.values(), default=0)
    aspect = max(span_x, span_y) / max(1.0, min(span_x, span_y))
    if len(shapes) >= 2 and aspect >= 2.5 and max_deg <= 2:
        return "sequential_pipeline", density

    # Rank alignment check for hierarchical layered graphs
    if len(shapes) >= 3 and directed_pairs:
        xs_c = sorted(float(s.get("x", 0.0)) + float(s.get("width", 0.0)) / 2.0 for s in shapes)
        ys_c = sorted(float(s.get("y", 0.0)) + float(s.get("height", 0.0)) / 2.0 for s in shapes)

        def _count_bands(vals: List[float]) -> int:
            bands = 1
            anchor = vals[0]
            for v in vals[1:]:
                if abs(v - anchor) > 15.0:
                    bands += 1
                    anchor = v
            return bands

        x_bands = _count_bands(xs_c)
        y_bands = _count_bands(ys_c)
        forward_x = sum(
            1
            for s1, s2 in directed_pairs
            if float(s2.get("x", 0.0)) > float(s1.get("x", 0.0)) + 15.0
        )
        forward_y = sum(
            1
            for s1, s2 in directed_pairs
            if float(s2.get("y", 0.0)) > float(s1.get("y", 0.0)) + 15.0
        )
        n_edges = len(directed_pairs)
        if (x_bands >= 2 and forward_x / n_edges >= 0.75) or (
            y_bands >= 2 and forward_y / n_edges >= 0.75
        ):
            return "hierarchical_layered", density

    return "freeform", density


def build_scene_routing_context(
    elements: List[dict], exclude_arrow_ids: Optional[set] = None
) -> SceneRoutingContext:
    """Build a deterministic SceneRoutingContext from active scene elements."""
    exclude = exclude_arrow_ids or set()
    active = [e for e in elements if not e.get("isDeleted")]
    shapes = [
        e
        for e in active
        if e.get("type") in ("rectangle", "diamond", "ellipse")
        and (e.get("customData") or {}).get("type") not in ("code_block_header",)
        and (e.get("customData") or {}).get("allow_overlap") is not True
    ]
    frames = [e for e in active if e.get("type") == "frame"]
    arrows = [e for e in active if e.get("type") in ("arrow", "line")]
    texts = [e for e in active if e.get("type") == "text"]

    shape_boxes: Dict[str, Tuple[float, float, float, float]] = {}
    for s in shapes:
        sid = s.get("id")
        if not sid:
            continue
        sx = float(s.get("x", 0.0))
        sy = float(s.get("y", 0.0))
        sw = float(s.get("width", s.get("w", 0.0)))
        sh = float(s.get("height", s.get("h", 0.0)))
        shape_boxes[str(sid)] = (sx, sy, sx + sw, sy + sh)

    frame_headers: List[Tuple[float, float, float, float]] = []
    for f in frames:
        fx = float(f.get("x", 0.0))
        fy = float(f.get("y", 0.0))
        fw = float(f.get("width", f.get("w", 0.0)))
        fh = float(f.get("height", f.get("h", 0.0)))
        frame_headers.append((fx, fy, fx + fw, min(fy + fh, fy + FRAME_HEADER_HEIGHT)))

    existing_segments: Dict[str, List[Tuple[Tuple[float, float], Tuple[float, float]]]] = {}
    for a in arrows:
        aid = a.get("id")
        if aid and aid not in exclude:
            existing_segments[str(aid)] = _arrow_world_segments(a)

    label_boxes: List[Tuple[float, float, float, float, Optional[str]]] = []
    for t in texts:
        cid = t.get("containerId")
        # Include standalone text and bound arrow labels (shape-bound labels sit inside shapes)
        if cid and cid in shape_boxes:
            continue
        if cid and cid in exclude:
            continue
        tx = float(t.get("x", 0.0))
        ty = float(t.get("y", 0.0))
        tw = float(t.get("width", 40.0))
        th = float(t.get("height", 20.0))
        pad = 6.0
        label_boxes.append((tx - pad, ty - pad, tx + tw + pad, ty + th + pad, cid))

    structure, density = _classify_scene_structure(shapes, frames, arrows)
    return SceneRoutingContext(
        shapes=shapes,
        shape_boxes=shape_boxes,
        frames=frames,
        frame_headers=frame_headers,
        existing_segments=existing_segments,
        label_boxes=label_boxes,
        density=density,
        structure=structure,
    )


def get_shape_port(
    shape: dict, face: str, offset: float = 0.0
) -> Tuple[Tuple[float, float], Tuple[int, int]]:
    """Calculate connection boundary point and normal vector on a shape's face."""
    x = float(shape.get("x", 0.0))
    y = float(shape.get("y", 0.0))
    w = float(shape.get("width", shape.get("w", 0.0)))
    h = float(shape.get("height", shape.get("h", 0.0)))
    stype = shape.get("type", shape.get("shape", "rectangle"))
    cx = x + w / 2.0
    cy = y + h / 2.0

    if stype == "ellipse":
        rx = max(w / 2.0, 1.0)
        ry = max(h / 2.0, 1.0)
        if face == "top":
            off = max(-rx * 0.75, min(rx * 0.75, offset))
            ratio = off / rx
            dy = ry * math.sqrt(max(0.0, 1.0 - ratio * ratio))
            return (cx + off, cy - dy), (0, -1)
        elif face == "bottom":
            off = max(-rx * 0.75, min(rx * 0.75, offset))
            ratio = off / rx
            dy = ry * math.sqrt(max(0.0, 1.0 - ratio * ratio))
            return (cx + off, cy + dy), (0, 1)
        elif face == "left":
            off = max(-ry * 0.75, min(ry * 0.75, offset))
            ratio = off / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - ratio * ratio))
            return (cx - dx, cy + off), (-1, 0)
        elif face == "right":
            off = max(-ry * 0.75, min(ry * 0.75, offset))
            ratio = off / ry
            dx = rx * math.sqrt(max(0.0, 1.0 - ratio * ratio))
            return (cx + dx, cy + off), (1, 0)

    elif stype == "diamond":
        rx = max(w / 2.0, 1.0)
        ry = max(h / 2.0, 1.0)
        if face == "top":
            off = max(-rx * 0.75, min(rx * 0.75, offset))
            py = cy - ry * (1.0 - abs(off) / rx)
            return (cx + off, py), (0, -1)
        elif face == "bottom":
            off = max(-rx * 0.75, min(rx * 0.75, offset))
            py = cy + ry * (1.0 - abs(off) / rx)
            return (cx + off, py), (0, 1)
        elif face == "left":
            off = max(-ry * 0.75, min(ry * 0.75, offset))
            px = cx - rx * (1.0 - abs(off) / ry)
            return (px, cy + off), (-1, 0)
        elif face == "right":
            off = max(-ry * 0.75, min(ry * 0.75, offset))
            px = cx + rx * (1.0 - abs(off) / ry)
            return (px, cy + off), (1, 0)

    # Default: Rectangle
    mx = min(10.0, w * 0.25)
    my = min(10.0, h * 0.25)
    if face == "top":
        px = max(x + mx, min(x + w - mx, cx + offset))
        return (px, y), (0, -1)
    elif face == "bottom":
        px = max(x + mx, min(x + w - mx, cx + offset))
        return (px, y + h), (0, 1)
    elif face == "left":
        py = max(y + my, min(y + h - my, cy + offset))
        return (x, py), (-1, 0)
    elif face == "right":
        py = max(y + my, min(y + h - my, cy + offset))
        return (x + w, py), (1, 0)

    raise SceneError(f"Unsupported face: {face}")


def choose_natural_faces(
    source: dict, target: dict, preferred: Optional[Tuple[str, str]] = None
) -> List[Tuple[str, str]]:
    """Determine candidate (source_face, target_face) pairs ordered by geometric preference."""
    if preferred:
        return [preferred]

    sx = float(source.get("x", 0.0))
    sy = float(source.get("y", 0.0))
    sw = float(source.get("width", source.get("w", 0.0)))
    sh = float(source.get("height", source.get("h", 0.0)))

    tx = float(target.get("x", 0.0))
    ty = float(target.get("y", 0.0))
    tw = float(target.get("width", target.get("w", 0.0)))
    th = float(target.get("height", target.get("h", 0.0)))

    scx, scy = sx + sw / 2.0, sy + sh / 2.0
    tcx, tcy = tx + tw / 2.0, ty + th / 2.0
    dx = tcx - scx
    dy = tcy - scy

    # Target is clearly below source
    if ty >= sy + sh - 5.0:
        if abs(dx) < 80.0:
            return [("bottom", "top"), ("right", "top"), ("left", "top")]
        side_src = "right" if dx > 0 else "left"
        side_dst = "left" if dx > 0 else "right"
        if abs(dx) > abs(dy) * 1.5:
            return [(side_src, side_dst), ("bottom", "top"), (side_src, "top"), ("bottom", side_dst)]
        return [("bottom", "top"), (side_src, "top"), ("bottom", side_dst), (side_src, side_dst)]

    # Target is clearly above source
    elif ty + th <= sy + 5.0:
        if abs(dx) < 80.0:
            return [("top", "bottom"), ("right", "bottom"), ("left", "bottom")]
        side_src = "right" if dx > 0 else "left"
        side_dst = "left" if dx > 0 else "right"
        if abs(dx) > abs(dy) * 1.5:
            return [(side_src, side_dst), ("top", "bottom"), (side_src, "bottom"), ("top", side_dst)]
        return [("top", "bottom"), (side_src, "bottom"), ("top", side_dst), (side_src, side_dst)]

    # Target is to the right
    elif tx >= sx + sw - 5.0:
        vert_src = "bottom" if dy > 0 else "top"
        return [("right", "left"), (vert_src, "left"), ("right", vert_src)]

    # Target is to the left
    elif tx + tw <= sx + 5.0:
        vert_src = "bottom" if dy > 0 else "top"
        return [("left", "right"), (vert_src, "right"), ("left", vert_src)]

    # Overlapping or tight bounding boxes
    return [("bottom", "top"), ("right", "left"), ("top", "bottom"), ("left", "right")]


def segment_intersects_rect(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    rect: Tuple[float, float, float, float],
    margin: float = 2.0,
) -> bool:
    """Liang-Barsky segment clipping check against a rectangle interior."""
    bx1, by1, bx2, by2 = rect
    rx1, ry1, rx2, ry2 = bx1 + margin, by1 + margin, bx2 - margin, by2 - margin
    if rx1 >= rx2 or ry1 >= ry2:
        return False
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    p = [-dx, dx, -dy, dy]
    q = [p1[0] - rx1, rx2 - p1[0], p1[1] - ry1, ry2 - p1[1]]
    u1, u2 = 0.0, 1.0
    for k in range(4):
        if p[k] == 0:
            if q[k] < 0:
                return False
        else:
            t = q[k] / p[k]
            if p[k] < 0:
                if t > u2:
                    return False
                if t > u1:
                    u1 = t
            else:
                if t < u1:
                    return False
                if t < u2:
                    u2 = t
    return u1 <= u2


def simplify_polyline(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Remove redundant collinear points and zero-length steps from a polyline."""
    if len(pts) <= 2:
        return pts
    result = [pts[0]]
    for i in range(1, len(pts) - 1):
        prev = result[-1]
        curr = pts[i]
        nxt = pts[i + 1]
        # Skip zero length
        if abs(curr[0] - prev[0]) < 1e-4 and abs(curr[1] - prev[1]) < 1e-4:
            continue
        # Skip collinear horizontal or vertical
        if (abs(prev[0] - curr[0]) < 1e-4 and abs(curr[0] - nxt[0]) < 1e-4) or (
            abs(prev[1] - curr[1]) < 1e-4 and abs(curr[1] - nxt[1]) < 1e-4
        ):
            continue
        result.append(curr)
    if abs(pts[-1][0] - result[-1][0]) > 1e-4 or abs(pts[-1][1] - result[-1][1]) > 1e-4:
        result.append(pts[-1])
    return result


def route_orthogonal_connector(
    source: dict,
    target: dict,
    obstacles: List[dict],
    clearance: float = 15.0,
    bend_penalty: float = 30.0,
    s_offset: float = 0.0,
    t_offset: float = 0.0,
    preferred_faces: Optional[Tuple[str, str]] = None,
) -> List[Tuple[float, float]]:
    """Route an obstacle-aware orthogonal connector around diagram components.

    Returns a list of absolute (x, y) coordinates from source border to target border.
    """
    obs_boxes = []
    source_id = source.get("id")
    target_id = target.get("id")

    for o in obstacles:
        oid = o.get("id")
        if oid in (source_id, target_id):
            continue
        ox = float(o.get("x", 0.0))
        oy = float(o.get("y", 0.0))
        ow = float(o.get("width", o.get("w", 0.0)))
        oh = float(o.get("height", o.get("h", 0.0)))
        obs_boxes.append((ox - clearance, oy - clearance, ox + ow + clearance, oy + oh + clearance))

    endpoint_boxes = [
        (
            float(el.get("x", 0.0)),
            float(el.get("y", 0.0)),
            float(el.get("x", 0.0)) + float(el.get("width", el.get("w", 0.0))),
            float(el.get("y", 0.0)) + float(el.get("height", el.get("h", 0.0))),
        )
        for el in (source, target)
    ]

    def _hits_boxes(p1: Tuple[float, float], p2: Tuple[float, float], boxes: list[tuple[float, float, float, float]]) -> bool:
        eps = 0.5
        x1, y1 = p1
        x2, y2 = p2
        if abs(y1 - y2) < 1e-4:  # Horizontal segment
            y = y1
            min_x, max_x = min(x1, x2), max(x1, x2)
            for ox1, oy1, ox2, oy2 in boxes:
                if oy1 + eps < y < oy2 - eps:
                    if max(min_x, ox1 + eps) < min(max_x, ox2 - eps):
                        return True
        elif abs(x1 - x2) < 1e-4:  # Vertical segment
            x = x1
            min_y, max_y = min(y1, y2), max(y1, y2)
            for ox1, oy1, ox2, oy2 in boxes:
                if ox1 + eps < x < ox2 - eps:
                    if max(min_y, oy1 + eps) < min(max_y, oy2 - eps):
                        return True
        else:
            for b in boxes:
                if segment_intersects_rect(p1, p2, b, margin=eps):
                    return True
        return False

    def seg_hits_obs(p1: Tuple[float, float], p2: Tuple[float, float], include_endpoints: bool = True) -> bool:
        if _hits_boxes(p1, p2, obs_boxes):
            return True
        if include_endpoints and _hits_boxes(p1, p2, endpoint_boxes):
            return True
        return False

    candidate_pairs = choose_natural_faces(source, target, preferred=preferred_faces)
    best_path = None
    best_cost = float("inf")

    for s_face, t_face in candidate_pairs:
        p_start, v_start = get_shape_port(source, s_face, s_offset)
        p_end, v_end = get_shape_port(target, t_face, t_offset)

        stub_s = None
        for stub_dist in (clearance, min(clearance, 4.0), 0.0):
            cand_s = (p_start[0] + v_start[0] * stub_dist, p_start[1] + v_start[1] * stub_dist)
            if stub_dist == 0.0 or not seg_hits_obs(p_start, cand_s, include_endpoints=False):
                stub_s = cand_s
                break
        stub_e = None
        for stub_dist in (clearance, min(clearance, 4.0), 0.0):
            cand_e = (p_end[0] + v_end[0] * stub_dist, p_end[1] + v_end[1] * stub_dist)
            if stub_dist == 0.0 or not seg_hits_obs(cand_e, p_end, include_endpoints=False):
                stub_e = cand_e
                break
        if stub_s is None or stub_e is None:
            continue

        # Build sparse orthogonal coordinate grid
        xs = {p_start[0], stub_s[0], stub_e[0], p_end[0]}
        ys = {p_start[1], stub_s[1], stub_e[1], p_end[1]}

        for ox1, oy1, ox2, oy2 in obs_boxes:
            xs.add(ox1)
            xs.add(ox2)
            ys.add(oy1)
            ys.add(oy2)

        sorted_x = sorted(xs)
        sorted_y = sorted(ys)

        # Add corridor centers between obstacle boundaries
        mid_x = [
            (sorted_x[i] + sorted_x[i + 1]) / 2.0
            for i in range(len(sorted_x) - 1)
            if sorted_x[i + 1] - sorted_x[i] > 10.0
        ]
        mid_y = [
            (sorted_y[i] + sorted_y[i + 1]) / 2.0
            for i in range(len(sorted_y) - 1)
            if sorted_y[i + 1] - sorted_y[i] > 10.0
        ]

        all_x = sorted(set(sorted_x + mid_x))
        all_y = sorted(set(sorted_y + mid_y))

        # A* pathfinding on integer-indexed corridor grid
        start_xi = all_x.index(stub_s[0])
        start_yi = all_y.index(stub_s[1])
        target_xi = all_x.index(stub_e[0])
        target_yi = all_y.index(stub_e[1])
        target_pt = stub_e
        init_dir = "V" if abs(v_start[1]) > 0 else "H"
        pq = [
            (
                abs(stub_s[0] - target_pt[0]) + abs(stub_s[1] - target_pt[1]),
                0.0,
                start_xi,
                start_yi,
                init_dir,
                [p_start, stub_s],
            )
        ]
        visited: dict[tuple[int, int, str], float] = {}
        path_found = None
        total_cost = float("inf")

        while pq:
            f, g, xi, yi, cdir, path = heapq.heappop(pq)
            cx, cy = all_x[xi], all_y[yi]
            if xi == target_xi and yi == target_yi:
                path_found = path + [p_end]
                total_cost = g
                break

            state_key = (xi, yi, cdir)
            if state_key in visited and visited[state_key] <= g:
                continue
            visited[state_key] = g

            # Step along horizontal corridor
            for nxi in (xi - 1, xi + 1):
                if 0 <= nxi < len(all_x):
                    nx = all_x[nxi]
                    if not seg_hits_obs((cx, cy), (nx, cy), include_endpoints=True):
                        dist = abs(nx - cx)
                        turn_cost = bend_penalty if cdir == "V" else 0.0
                        ng = g + dist + turn_cost
                        h = abs(nx - target_pt[0]) + abs(cy - target_pt[1])
                        heapq.heappush(pq, (ng + h, ng, nxi, yi, "H", path + [(nx, cy)]))

            # Step along vertical corridor
            for nyi in (yi - 1, yi + 1):
                if 0 <= nyi < len(all_y):
                    ny = all_y[nyi]
                    if not seg_hits_obs((cx, cy), (cx, ny), include_endpoints=True):
                        dist = abs(ny - cy)
                        turn_cost = bend_penalty if cdir == "H" else 0.0
                        ng = g + dist + turn_cost
                        h = abs(cx - target_pt[0]) + abs(ny - target_pt[1])
                        heapq.heappush(pq, (ng + h, ng, xi, nyi, "V", path + [(cx, ny)]))

        if path_found and total_cost < best_cost:
            best_cost = total_cost
            best_path = simplify_polyline(path_found)

    if best_path:
        return best_path

    # Fallback to direct boundary attachment if completely enclosed
    p_start, _ = get_shape_port(source, candidate_pairs[0][0], s_offset)
    p_end, _ = get_shape_port(target, candidate_pairs[0][1], t_offset)
    return [p_start, p_end]


def position_connector_label(
    route_points: List[Tuple[float, float]],
    label_w: float,
    label_h: float,
    obstacles: Optional[List[dict]] = None,
) -> Tuple[float, float]:
    """Position a connector label along clear corridor segments away from obstacles."""
    if len(route_points) < 2:
        return (route_points[0][0] - label_w / 2.0, route_points[0][1] - label_h / 2.0)

    # Segment candidate ranking: length, not immediate stub
    candidates = []
    n_segs = len(route_points) - 1

    for i in range(n_segs):
        p1 = route_points[i]
        p2 = route_points[i + 1]
        length = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        # Penalty for first stub (near source) or last stub (near arrowhead)
        score = length
        if i == 0 and n_segs > 1:
            score -= 40.0
        if i == n_segs - 1 and n_segs > 1:
            score -= 40.0
        candidates.append((score, i, p1, p2))

    candidates.sort(key=lambda c: c[0], reverse=True)
    best_x, best_y = 0.0, 0.0
    min_collisions = float("inf")

    obs_rects = []
    if obstacles:
        for o in obstacles:
            ox = float(o.get("x", 0.0))
            oy = float(o.get("y", 0.0))
            ow = float(o.get("width", o.get("w", 0.0)))
            oh = float(o.get("height", o.get("h", 0.0)))
            obs_rects.append((ox, oy, ox + ow, oy + oh))

    for _, _, p1, p2 in candidates:
        mx = (p1[0] + p2[0]) / 2.0
        my = (p1[1] + p2[1]) / 2.0
        lx = mx - label_w / 2.0
        ly = my - label_h / 2.0

        # Count obstacle overlaps
        colls = 0
        for bx1, by1, bx2, by2 in obs_rects:
            if not (lx + label_w < bx1 or lx > bx2 or ly + label_h < by1 or ly > by2):
                colls += 1

        if colls < min_collisions:
            min_collisions = colls
            best_x, best_y = lx, ly
            if colls == 0:
                break

    return best_x, best_y


def reroute_scene_arrows(
    elements: List[dict],
    clearance: float = 15.0,
    lane_spacing: float = 24.0,
    only_elbowed: bool = False,
) -> None:
    """Reroute connected arrows in a scene with obstacle avoidance and multi-edge lanes."""
    active = [e for e in elements if not e.get("isDeleted")]
    shapes = [
        e
        for e in active
        if e.get("type") in ("rectangle", "diamond", "ellipse")
        and (e.get("customData") or {}).get("type") not in ("code_block_header",)
    ]
    arrows = [e for e in active if e.get("type") in ("arrow", "line")]
    texts = [e for e in active if e.get("type") == "text"]

    element_index = {e["id"]: e for e in active if e.get("id")}
    bound_labels = {t["containerId"]: t for t in texts if t.get("containerId")}

    # Group connected arrows by canonical shape pair to allocate separate lanes
    pair_arrows: Dict[Tuple[str, str], List[dict]] = {}
    for a in arrows:
        if a.get("locked"):
            continue
        sb = (a.get("startBinding") or {}).get("elementId")
        eb = (a.get("endBinding") or {}).get("elementId")
        if sb and eb and sb in element_index and eb in element_index:
            pair_key = (min(str(sb), str(eb)), max(str(sb), str(eb)))
            pair_arrows.setdefault(pair_key, []).append(a)

    for pair_key, group in pair_arrows.items():
        total_in_pair = len(group)
        for idx, a in enumerate(group):
            sb = (a.get("startBinding") or {}).get("elementId")
            eb = (a.get("endBinding") or {}).get("elementId")
            source_el = element_index[sb]
            target_el = element_index[eb]

            # Calculate lane slot offset
            slot_offset = (idx - (total_in_pair - 1) / 2.0) * lane_spacing if total_in_pair > 1 else 0.0

            mode = resolve_arrow_routing_mode(a, default="auto")
            is_elbowed = bool(a.get("elbowed"))
            if only_elbowed and not is_elbowed and mode != "orthogonal":
                continue

            if mode == "straight":
                from .layout import boundary_point

                s_node = {
                    "shape": source_el.get("type", "rectangle"),
                    "x": float(source_el.get("x", 0.0)),
                    "y": float(source_el.get("y", 0.0)),
                    "w": float(source_el.get("width", 0.0)),
                    "h": float(source_el.get("height", 0.0)),
                    "angle": float(source_el.get("angle", 0.0)),
                }
                t_node = {
                    "shape": target_el.get("type", "rectangle"),
                    "x": float(target_el.get("x", 0.0)),
                    "y": float(target_el.get("y", 0.0)),
                    "w": float(target_el.get("width", 0.0)),
                    "h": float(target_el.get("height", 0.0)),
                    "angle": float(target_el.get("angle", 0.0)),
                }
                p_start = boundary_point(s_node, t_node, 1)
                p_end = boundary_point(t_node, s_node, -1)
                if total_in_pair > 1:
                    dx = p_end[0] - p_start[0]
                    dy = p_end[1] - p_start[1]
                    dist = math.hypot(dx, dy)
                    if dist > 1e-4:
                        nx, ny = -dy / dist, dx / dist
                        p_start = (p_start[0] + nx * slot_offset, p_start[1] + ny * slot_offset)
                        p_end = (p_end[0] + nx * slot_offset, p_end[1] + ny * slot_offset)
                a["elbowed"] = False
                world_pts = [p_start, p_end]
            else:
                # Check direct line collision
                cand_pairs = choose_natural_faces(source_el, target_el)
                default_s_face, default_t_face = cand_pairs[0]
                p_start, _ = get_shape_port(source_el, default_s_face, slot_offset)
                p_end, _ = get_shape_port(target_el, default_t_face, slot_offset)

                has_direct_collision = False
                for s in shapes:
                    if s.get("id") in (sb, eb):
                        continue
                    sx = float(s.get("x", 0.0))
                    sy = float(s.get("y", 0.0))
                    sw = float(s.get("width", s.get("w", 0.0)))
                    sh = float(s.get("height", s.get("h", 0.0)))
                    if segment_intersects_rect(p_start, p_end, (sx, sy, sx + sw, sy + sh), margin=2.0):
                        has_direct_collision = True
                        break

                if mode == "orthogonal" or is_elbowed or has_direct_collision:
                    world_pts = route_orthogonal_connector(
                        source_el,
                        target_el,
                        obstacles=shapes,
                        clearance=clearance,
                        s_offset=slot_offset,
                        t_offset=slot_offset,
                    )
                    if mode == "orthogonal" or is_elbowed or len(world_pts) > 2:
                        a["elbowed"] = True
                else:
                    world_pts = [p_start, p_end]

            # Convert world points to Excalidraw arrow format (x, y + relative points)
            origin_x, origin_y = world_pts[0]
            rel_points = [[pt[0] - origin_x, pt[1] - origin_y] for pt in world_pts]

            a["x"] = origin_x
            a["y"] = origin_y
            a["points"] = rel_points
            all_x = [pt[0] for pt in world_pts]
            all_y = [pt[1] for pt in world_pts]
            a["width"] = max(all_x) - min(all_x)
            a["height"] = max(all_y) - min(all_y)

            # Position bound label along clear route segment
            arrow_lbl = bound_labels.get(a.get("id"))
            if arrow_lbl:
                lw = float(arrow_lbl.get("width", 80.0))
                lh = float(arrow_lbl.get("height", 25.0))
                lx, ly = position_connector_label(world_pts, lw, lh, obstacles=shapes)
                arrow_lbl["x"] = lx
                arrow_lbl["y"] = ly
