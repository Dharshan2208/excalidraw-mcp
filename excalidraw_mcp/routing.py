"""Obstacle-aware orthogonal connector routing and label positioning.

Provides Manhattan A* routing around diagram components, frame-aware corridors,
multiple-edge offset handling, and collision-free connector label placement.
"""

import heapq
import math
from typing import Any, Dict, List, Optional, Tuple

from .errors import SceneError


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
    if face == "top":
        px = max(x + 10.0, min(x + w - 10.0, cx + offset))
        return (px, y), (0, -1)
    elif face == "bottom":
        px = max(x + 10.0, min(x + w - 10.0, cx + offset))
        return (px, y + h), (0, 1)
    elif face == "left":
        py = max(y + 10.0, min(y + h - 10.0, cy + offset))
        return (x, py), (-1, 0)
    elif face == "right":
        py = max(y + 10.0, min(y + h - 10.0, cy + offset))
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
        return [("bottom", "top"), (side_src, "top"), ("bottom", side_dst)]

    # Target is clearly above source
    elif ty + th <= sy + 5.0:
        if abs(dx) < 80.0:
            return [("top", "bottom"), ("right", "bottom"), ("left", "bottom")]
        side_src = "right" if dx > 0 else "left"
        side_dst = "left" if dx > 0 else "right"
        return [("top", "bottom"), (side_src, "bottom"), ("top", side_dst)]

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

    def seg_hits_obs(p1: Tuple[float, float], p2: Tuple[float, float]) -> bool:
        eps = 0.5
        x1, y1 = p1
        x2, y2 = p2
        if abs(y1 - y2) < 1e-4:  # Horizontal segment
            y = y1
            min_x, max_x = min(x1, x2), max(x1, x2)
            for ox1, oy1, ox2, oy2 in obs_boxes:
                if oy1 + eps < y < oy2 - eps:
                    if max(min_x, ox1 + eps) < min(max_x, ox2 - eps):
                        return True
        elif abs(x1 - x2) < 1e-4:  # Vertical segment
            x = x1
            min_y, max_y = min(y1, y2), max(y1, y2)
            for ox1, oy1, ox2, oy2 in obs_boxes:
                if ox1 + eps < x < ox2 - eps:
                    if max(min_y, oy1 + eps) < min(max_y, oy2 - eps):
                        return True
        else:
            for b in obs_boxes:
                if segment_intersects_rect(p1, p2, b, margin=eps):
                    return True
        return False

    candidate_pairs = choose_natural_faces(source, target, preferred=preferred_faces)
    best_path = None
    best_cost = float("inf")

    for s_face, t_face in candidate_pairs:
        p_start, v_start = get_shape_port(source, s_face, s_offset)
        p_end, v_end = get_shape_port(target, t_face, t_offset)

        stub_s = (p_start[0] + v_start[0] * clearance, p_start[1] + v_start[1] * clearance)
        stub_e = (p_end[0] + v_end[0] * clearance, p_end[1] + v_end[1] * clearance)

        if seg_hits_obs(p_start, stub_s) or seg_hits_obs(stub_e, p_end):
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

        # A* pathfinding on corridor grid
        target_pt = stub_e
        init_dir = "V" if abs(v_start[1]) > 0 else "H"
        pq = [
            (
                abs(stub_s[0] - target_pt[0]) + abs(stub_s[1] - target_pt[1]),
                0.0,
                stub_s[0],
                stub_s[1],
                init_dir,
                [p_start, stub_s],
            )
        ]
        visited = {}
        path_found = None
        total_cost = float("inf")

        while pq:
            f, g, cx, cy, cdir, path = heapq.heappop(pq)
            if (cx, cy) == target_pt:
                path_found = path + [p_end]
                total_cost = g
                break

            state_key = (cx, cy, cdir)
            if state_key in visited and visited[state_key] <= g:
                continue
            visited[state_key] = g

            xi = all_x.index(cx) if cx in all_x else -1
            yi = all_y.index(cy) if cy in all_y else -1

            # Step along horizontal corridor
            for nxi in (xi - 1, xi + 1):
                if 0 <= nxi < len(all_x):
                    nx = all_x[nxi]
                    if not seg_hits_obs((cx, cy), (nx, cy)):
                        dist = abs(nx - cx)
                        turn_cost = bend_penalty if cdir == "V" else 0.0
                        ng = g + dist + turn_cost
                        h = abs(nx - target_pt[0]) + abs(cy - target_pt[1])
                        heapq.heappush(pq, (ng + h, ng, nx, cy, "H", path + [(nx, cy)]))

            # Step along vertical corridor
            for nyi in (yi - 1, yi + 1):
                if 0 <= nyi < len(all_y):
                    ny = all_y[nyi]
                    if not seg_hits_obs((cx, cy), (cx, ny)):
                        dist = abs(ny - cy)
                        turn_cost = bend_penalty if cdir == "H" else 0.0
                        ng = g + dist + turn_cost
                        h = abs(cx - target_pt[0]) + abs(ny - target_pt[1])
                        heapq.heappush(pq, (ng + h, ng, cx, ny, "V", path + [(cx, ny)]))

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
        and not ((e.get("customData") or {}).get("type") in ("code_block_header",))
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
        if sb in element_index and eb in element_index:
            pair_key = (min(sb, eb), max(sb, eb))
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

            is_elbowed = bool(a.get("elbowed"))

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

            if is_elbowed or has_direct_collision:
                world_pts = route_orthogonal_connector(
                    source_el,
                    target_el,
                    obstacles=shapes,
                    clearance=clearance,
                    s_offset=slot_offset,
                    t_offset=slot_offset,
                )
                if is_elbowed or len(world_pts) > 2:
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
