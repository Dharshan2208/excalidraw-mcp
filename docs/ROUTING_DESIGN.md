# Scene-Aware Connector Routing — Technical Investigation & Design Proposal (`ROUTING_DESIGN.md`)

**Status:** Design Proposal (Investigation Only — No Code Modified)  
**Target Codebase:** `excalidraw-mcp` (`v0.4.0`)

---

## 1. Executive Summary

`excalidraw-mcp` currently treats connector routing as a binary toggle (`elbowed: bool = False`): either a 2-point straight line (`boundary_point`) or an orthogonal Manhattan A* polyline (`route_orthogonal_connector`). Meanwhile, scene-wide passes (`resolve_scene_layout`, `auto_fix_layout`, `reroute_connectors`) invoke `reroute_scene_arrows(..., only_elbowed=False)`, which **forcibly converts** colliding straight arrows into `elbowed=True` and snaps non-colliding straight arrows to axis-aligned face centers—destroying intentional diagonals and custom geometry.

This document proposes a **Scene-Aware Connector Routing Engine** where **straight/diagonal**, **orthogonal (Manhattan)**, and **curved (`roundness: {"type": 2}`)** connectors coexist naturally in the same diagram. The AI agent retains explicit control (`routing_mode`: `"auto" | "straight" | "orthogonal" | "curved"`) at both diagram and per-connector levels, while `"auto"` uses deterministic, measurable scene-analysis criteria to choose the cleanest style without mutating locked or explicitly styled connectors.

---

## 2. Existing Implementation Analysis

### 2.1 Data Model & Normalization (`elements.py`, `document.py`, `models.py`)
- **Arrow schema (`elements.py:202-222`, `document.py:70-126`):**
  - Stored as `"type": "arrow"` with `x, y` (start world coordinate when unrotated), `points` (`[[0, 0], ...]`), `width, height`, `startBinding`, `endBinding`, `startArrowhead`, `endArrowhead`, `lastCommittedPoint`, `elbowed: bool`, and `roundness` (`None` or `{"type": 1 | 2 | 3}`).
  - `_normalize_arrow` shifts `x, y` by `points[0]` for unrotated arrows (`angle == 0`) and recomputes `width`/`height` from point extents.
  - `startBinding`/`endBinding` are hardcoded across `connect`, `batch_mutate`, and `draw_graph` (`service.py:1006-1019, 2226-2239, 3189-3202`) to `{"elementId": ..., "focus": 0, "gap": 0, "fixedPoint": [0.5, 0.5], "mode": "inside"}`.
  - Unknown fields and `customData` survive all round-trips (`models.py:103`, `importer.py`, `obsidian.py`, `sharing.py`).
- **Labels:** Stored as separate `type: "text"` elements with `containerId == arrow["id"]`. `_center_label` (`service.py:113-135`) calls `position_connector_label(world_pts, lw, lh)` (without passing `obstacles`) when `len(points) > 2`, and uses endpoint midpoint for 2-point arrows.

### 2.2 Routing & Layout Subsystems (`routing.py`, `layout.py`, `auto_fix.py`, `service.py`)
- **`get_shape_port(shape, face, offset)` (`routing.py:14-86`):** Computes boundary ports + outward normals for `rectangle`, `ellipse`, and `diamond` (clamping rectangle insets to `min(10.0, w*0.25)`).
- **`choose_natural_faces(source, target, preferred)` (`routing.py:89-143`):** Selects candidate `(source_face, target_face)` pairs using only pairwise AABB/center heuristics (`ty >= sy + sh - 5.0`, `abs(dx) < 80.0`, `abs(dx) > abs(dy) * 1.5`).
- **`route_orthogonal_connector(...)` (`routing.py:203-390`):** Builds a sparse H/V grid from obstacle AABBs inflated by `clearance=15.0` plus corridor midpoints, and runs Manhattan A* minimizing `distance + 30.0 * bends`.
- **`reroute_scene_arrows(elements, clearance=15.0, lane_spacing=24.0, only_elbowed=False)` (`routing.py:452-549`):**
  - Groups unlocked bound arrows by canonical `(min(sb, eb), max(sb, eb))` pair to compute `slot_offset`.
  - When `only_elbowed=False` (used by `resolve_scene_layout`, `auto_fix_layout`, and `reroute_connectors`), checks straight-line collision only on `cand_pairs[0]`: if colliding or `elbowed=True`, routes orthogonally and sets `a["elbowed"] = True`; if non-colliding, overwrites `points` with `get_shape_port` on `cand_pairs[0]`.
- **`draw_graph` (`service.py:2940-3246`):** Emits straight `boundary_point` arrows (with `24.0` normal-vector lane offsets for parallel edges) and only runs `reroute_scene_arrows(..., only_elbowed=True)` if any edge has `elbowed=True`.

### 2.3 Rendering & Live Sync (`renderer.py`, `svg_renderer.py`, `live_server.py`)
- **Render-time fallback (`renderer.py:562-594`, `svg_renderer.py:383-416`):** Both renderers intercept `is_elbowed and len(points) == 2` and re-route on the fly during PNG/SVG export, while `live_server.py` draws raw `points`.
- **Curved arrows (`roundness: {"type": 2}`):** Validated and preserved by `document.py:212-215` and `elements.py:37-38`, and natively rendered as smooth Catmull-Rom splines by Excalidraw when `elbowed=False` and `len(points) >= 3`. However, `renderer.py:598` (`_draw_polyline`) and `svg_renderer.py:421` (`<polyline>`) currently ignore `roundness` on arrows and draw straight segments.

---

## 3. Confirmed Problems & Design Limitations

1. **Orthogonal Dominance & Silent Overwriting:** `reroute_scene_arrows(..., only_elbowed=False)` converts colliding straight arrows into `elbowed=True` and overwrites non-colliding diagonal `boundary_point` arrows with axis-aligned face-center ports. There is no way to mark an arrow as `"straight"` (must stay 2-point) vs `"auto"` (eligible for upgrade) vs `"manual"`.
2. **Pairwise Myopia:** `choose_natural_faces` and `route_orthogonal_connector` evaluate `(source, target)` against shape AABBs only. They ignore:
   - **Existing arrows** (causing edge-edge crossings and collinear overlapping lines).
   - **Frame headers & boundaries** (arrows cut through `frame` title bands `y..y+28`).
   - **Text & arrow labels** (`_center_label` doesn't pass `obstacles` to `position_connector_label`, and `position_connector_label` ignores other labels and arrows).
   - **Fan-in / fan-out on the same node** (`slot_offset` only separates arrows sharing the exact same `(source, target)` pair, not 3 arrows entering `B`'s left face from `A1, A2, A3`).
3. **Inconsistent Lifecycle & Render-Time Divergence:**
   - `update_element(elbowed=True|False)` updates the boolean flag without recomputing `points` or label coordinates.
   - `batch_mutate(action="move")` fails on single-end `elbowed` moves instead of calling `_reroute_connector` like `SceneService.move` does.
   - Moving a node (`_apply_move`) linearly shifts straight arrows without checking if the move created new obstacles on straight paths, or if moving a node now blocks a *non-incident* straight arrow.
   - `SceneService.reroute_connectors` exists in `service.py:1595` but is not exposed in `server.py`.
4. **No Curved Connector Support:** `GraphEdge` lacks `roundness`, `routing.py` cannot generate smooth multi-point curved waypoints, and `renderer.py`/`svg_renderer.py` do not render `roundness: {"type": 2}` curves or endpoint tangents for arrowheads.

---

## 4. Architectural Options Comparison

### Approach A: Pure Post-Hoc Repair (`auto_fix_layout` Only)
- **How it works:** `create_connector` and `draw_graph` always emit simple straight or naive A* arrows; `auto_fix_layout` (or a new tool) rewrites them at the end.
- **Pros:** Minimal changes to `connect` / `draw_graph`; fast incremental creation.
- **Cons:** Intermediate `preview` / `inspect_scene` calls show broken overlapping arrows; `auto_fix_layout` cannot distinguish an agent's intentional straight diagonal from an accidental collision; violates "don't silently destroy diagram structure."

### Approach B: Stateless Pairwise Router at Creation Time
- **How it works:** `connect` decides straight vs. orthogonal using only `(source, target, shapes)` at creation time.
- **Pros:** Predictable per-call; no global state needed.
- **Cons:** Blind to previously placed arrows, label boxes, and diagram structure (`layered` vs. `freeform`); arrows created first are never protected from later arrows crossing them; `draw_graph` still needs global ordering.

### Approach C: Unified Scene-Aware Routing Engine + Policy Metadata (**Recommended**)
- **How it works:** A shared `SceneRouter` evaluates a `SceneRoutingContext` (shapes, frames + header bands, existing arrow segments, occupied label boxes, density, and diagram structure). Every connector carries a persistent routing policy (`customData.routing_mode`: `"auto" | "straight" | "orthogonal" | "curved"`).
  - `"auto"` selects the best style deterministically from scene geometry.
  - `"straight"`, `"orthogonal"`, `"curved"` act as hard constraints honored across creation, moves, resizes, and `auto_fix_layout`.
  - Both single-connector creation (`create_connector`) and batch/graph generation (`draw_graph`, `reroute_scene_arrows`) use the exact same `SceneRouter`.
- **Pros:** Coexistence of straight, diagonal, orthogonal, and curved arrows; zero render-time divergence; explicit agent control + intelligent defaults; safe incremental updates.
- **Cons:** Slightly higher per-connector cost on creation (`O(E + V log V)`), mitigated by fast AABB/segment checks and spatial indexing.

---

## 5. Proposed Routing Architecture

```text
MCP Tool (create_connector / generate_diagram / update_element / batch_mutate / auto_fix_layout)
        │
        ▼
  Resolve Policy: routing_mode ("auto" | "straight" | "orthogonal" | "curved")
        │          + persist in customData["routing_mode"] (if explicit or "auto")
        ▼
  SceneRoutingContext (built once per batch or per call)
   ├── Obstacle AABBs (shapes, excluding allow_overlap)
   ├── Frame Header Bands (y .. y + 28px)
   ├── Existing Arrow Segments (for crossing & collinear overlap penalties)
   ├── Occupied Label AABBs (bound arrow labels + standalone text)
   └── Structure Classifier (clustered | sequential_pipeline | hierarchical_layered | freeform)
        │
        ▼
  SceneRouter.route_connector(source, target, policy, context)
   ├── "straight"   ──> boundary_point() + symmetric parallel normal offset
   ├── "orthogonal" ──> Multi-criteria Manhattan A* (corridors + crossing/frame/label costs)
   ├── "curved"     ──> Smooth 3+ point arc / detour spline (roundness={"type": 2}, elbowed=False)
   └── "auto"       ──> Deterministic Decision Tree (Section 7) -> dispatches to straight/orthogonal/curved
        │
        ▼
  Label Placement (position_connector_label with shapes + existing_labels + existing_arrows)
        │
        ▼
  Document State (stored points/x/y/width/height/elbowed/roundness — PNG & SVG render verbatim)
```

---

## 6. MCP API & Schema Proposal

Zero new MCP tools are required; all capabilities fit cleanly into existing tools (`12 core / 21 full`):

### 6.1 New Shared Type (`contracts.py`)
```python
RoutingMode = Literal["auto", "straight", "orthogonal", "curved"]
```
**Precedence:** `explicit routing_mode` > `elbowed=True` (maps to `"orthogonal"`) > `roundness="round"` on multi-point arrow (maps to `"curved"`) > default.

### 6.2 Should `auto` Be the Default?
- **`generate_diagram` (`format="graph"|"mermaid"|"architecture"`):** **Yes — default `routing_mode="auto"`** (when `elbowed` is not explicitly set). Generated diagrams have full node/edge/cluster context, so `"auto"` naturally picks straight edges for adjacent aligned nodes, orthogonal edges for skip-rank/cross-cluster/blocked edges, and clean lanes for parallel edges.
- **`create_connector` & `batch_mutate(action="connect")`:** **Recommend `routing_mode: RoutingMode = "auto"`** when `elbowed` is omitted, *unless* strict legacy 2-point behavior is needed (note: for 2 nearby unobstructed nodes, `"auto"` produces the exact same 2-point straight arrow as before, while automatically avoiding obstacles when one is in the way!). To preserve 100% backward compatibility for callers who explicitly want a raw straight line regardless of obstacles, they pass `routing_mode="straight"`.

### 6.3 Tool & Schema Additions
1. **`create_connector` (`server.py`):** Add `routing_mode: RoutingMode | None = None`, `source_face: Literal["top","bottom","left","right"] | None = None`, `target_face: Literal["top","bottom","left","right"] | None = None`.
2. **`update_element` (`server.py`):** Add `routing_mode: RoutingMode | None = None`. Changing `routing_mode` immediately re-routes the bound connector and repositions its label.
3. **`generate_diagram` (`server.py`) & `GraphEdge` (`contracts.py`):**
   - `generate_diagram`: Add `routing_mode: RoutingMode = "auto"` (diagram-level preference).
   - `GraphEdge`: Add `routing_mode: RoutingMode | None = None` (per-edge override) and `roundness: Roundness | None = None`.
4. **`BatchOperation` (`contracts.py`):** Add `routing_mode: RoutingMode | None = None` for `connect`, `add_arrow`, and `update_element`.
5. **Style Recommendation / Inspection (`inspect_scene`):**
   - In `inspect_scene(mode="summary" | "describe" | "element")`, include `routing_mode` and `recommended_routing_mode` (computed by `SceneRouter.recommend(arrow, context)`) in connector metadata so an agent can inspect and selectively override connectors without guessing.

### 6.4 Realistic Usage Examples
```json
// 1. Diagram-level orthogonal preference with a single straight shortcut override
{
  "tool": "generate_diagram",
  "arguments": {
    "format": "graph",
    "routing_mode": "orthogonal",
    "nodes": [{"id": "gw", "label": "API Gateway"}, {"id": "auth", "label": "Auth"}, {"id": "db", "label": "DB"}],
    "edges": [
      {"source": "gw", "target": "auth", "label": "verify"},
      {"source": "auth", "target": "db", "label": "query"},
      {"source": "gw", "target": "db", "label": "direct read", "routing_mode": "straight"}
    ]
  }
}

// 2. Scene-aware connector creation (auto-selects straight or orthogonal around obstacles)
{
  "tool": "create_connector",
  "arguments": {
    "source_id": "node-1",
    "target_id": "node-2",
    "label": "async event",
    "routing_mode": "auto"
  }
}
```

---

## 7. Scene-Aware Routing Decision Algorithm

### 7.1 Scene Analysis Metrics (`SceneRoutingContext`)
1. **Obstacles:** Active `rectangle`, `diamond`, `ellipse` shapes (excluding `code_block_header` and `customData.allow_overlap == True`).
2. **Frame Headers:** For each `frame`, reserve `[fx, fy, fx + fw, fy + 28.0]` as a high-penalty header band.
3. **Existing Segments & Labels:** All already-routed arrow segments and all text/label AABBs (padded by `6.0` px).
4. **Diagram Structure Classification:**
   - `clustered`: `>= 1` frame and `>= 50%` of shapes belong to frames.
   - `sequential_pipeline`: Aspect ratio `max(span_x, span_y) / max(1.0, min(span_x, span_y)) >= 2.5` and max node degree `<= 2`.
   - `hierarchical_layered`: `>= 2` rank bands aligned within `±15.0` px along the primary axis and `> 75%` of edges flow forward.
   - `freeform`: Otherwise.
5. **Density:** `density = sum(shape_area) / max(1.0, area(scene_bbox))`.

### 7.2 Deterministic Decision Tree (`routing_mode == "auto"`)
For a pair `(source, target)` with parallel edge count `m` and index `k` (`slot_offset = (k - (m - 1) / 2.0) * 24.0`):

1. **Compute Straight Candidate:**
   - `p_s, p_t = boundary_point(source, target)` (with normal offset `slot_offset` if `m > 1`, re-projected onto shape boundary).
   - `los_clear = not any(segment_intersects_rect(p_s, p_t, expand(obs, 8.0)) for obs in other_shapes)` AND no frame-header intersection.
   - `angle_deg = abs(degrees(atan2(p_t.y - p_s.y, p_t.x - p_s.x)))`.
   - `is_axis_aligned = min(angle_deg, abs(angle_deg - 90), abs(angle_deg - 180)) <= 5.0`.
   - `crossings = count_segment_intersections(p_s, p_t, existing_arrow_segments)`.

2. **Selection Rules (Strict Priority):**
   - **Rule 1 (Blocked Line-of-Sight):** If `not los_clear` -> **`orthogonal`**.
   - **Rule 2 (Parallel Multi-Edge):** If `m > 1`:
     - If `los_clear` and `hypot(p_t - p_s) < 320.0` and `structure in ("freeform", "sequential_pipeline")` -> **`curved`** (for opposing/parallel arcs, `roundness={"type": 2}`) or **parallel straight lanes** if `m == 2` and `crossings == 0`.
     - Otherwise -> **`orthogonal`** with distinct face-axis lane slots.
   - **Rule 3 (Structured Architecture / Cross-Frame / Skip-Rank):**
     - If `structure in ("hierarchical_layered", "clustered")` and `not is_axis_aligned` and (`cross_frame` or `is_back_or_skip_edge` or `density > 0.35`) -> **`orthogonal`** (keeps architecture diagrams crisp along rank/cluster corridors).
   - **Rule 4 (Crossing Avoidance):**
     - If `crossings > 0` and an `orthogonal` route achieves fewer crossings (`ortho_crossings < crossings`) with `<= 3` bends -> **`orthogonal`**.
   - **Rule 5 (Clean Straight / Diagonal):**
     - Otherwise -> **`straight`** (`elbowed=False`, 2 points).

### 7.3 Multi-Criteria Orthogonal A\* Objective
For `orthogonal` routes, minimize:
```text
Cost = manhattan_length
     + 45.0 * bend_count
     + 220.0 * arrow_crossing_count
     + 12.0 * collinear_arrow_overlap_px
     + 150.0 * frame_header_hits
     + 120.0 * label_box_hits
     + 0.15 * detour_overhead
```
- **Ordering in Batch/Graph Passes:** Sort unlocked edges by `(manhattan_dist, source_id, target_id, arrow_id)` so short local connections claim direct paths first and longer skip-edges route cleanly around them.
- **Fan-in / Fan-out Port Distribution:** Distribute multiple arrows attaching to the same `(node_id, face)` symmetrically across the face's safe span (capped at `min(24.0, safe_span / count)`), preventing port pile-ups.

### 7.4 Curved Connector Geometry (`routing_mode == "curved"`)
- Excalidraw renders smooth Catmull-Rom curves when `elbowed=False`, `roundness={"type": 2}`, and `len(points) >= 3`.
- For `curved` arrows:
  - If `m > 1` (parallel/bidirectional edges) and `los_clear`: generate a 3-point quadratic/Catmull-Rom arc `[[0, 0], [mid_x + nx * bow, mid_y + ny * bow], [dx, dy]]` where `bow = (k - (m - 1) / 2.0) * 32.0`.
  - If `not los_clear`: take the obstacle-avoiding orthogonal/visibility waypoints, simplify collinear points, and set `roundness={"type": 2}`, `elbowed=False`.
  - **Renderer Update Required:** Update `renderer.py` and `svg_renderer.py` to draw smooth Catmull-Rom / cubic Bezier curves when `not elbowed and (roundness or {}).get("type") == 2 and len(points) >= 3`, and orient arrowheads using the curve's endpoint tangent.

---

## 8. Routing Lifecycle & Mutation Behavior

| Lifecycle Event | Behavior |
| :--- | :--- |
| **Initial Creation (`connect`, `batch_mutate: connect`)** | Build `SceneRoutingContext` (excluding self), resolve `routing_mode`, compute route + symmetric parallel lanes if `m > 1`, place label against `shapes + existing_labels + existing_arrows`, store `customData["routing_mode"]`. |
| **Post-Layout (`draw_graph`, `draw_mermaid`, `draw_architecture`)** | After node/frame coordinates finalize, run `SceneRouter` across all edges ordered short-to-long, honoring per-edge overrides over diagram-level `routing_mode`. |
| **Node Move / Resize (`_apply_move`, `_apply_resize`, `batch_mutate`)** | Re-route all incident unlocked connectors according to their `routing_mode` (including `straight` if `routing_mode == "auto"` and newly blocked!). Also check non-incident `"auto"` straight arrows whose line-of-sight is now intersected by the moved/resized node, and reroute only those affected. |
| **Layout Repair (`auto_fix_layout`, `resolve_scene_layout`)** | **Never** convert `routing_mode == "straight"` or `locked == True` arrows to orthogonal. Only re-route `"orthogonal"`, `"curved"`, or `"auto"` arrows (or `"straight"` endpoints to match moved shapes while staying 2-point). |
| **Render Time (`renderer.py`, `svg_renderer.py`)** | Render stored `points` verbatim (with curve interpolation for `roundness.type == 2`). Remove/deprecate silent render-time re-routing once all creation/mutation paths store complete `points`. |

---

## 9. Integration with Existing Geometry & Diagnostics

- **Diagnostics (`auto_fix.py:diagnose_layout_issues`, `layout.py:check_diagram_geometry`):**
  - Keep `connector_collision` checks against non-endpoint shapes (sampling curved segments at `t = 0.0, 0.25, 0.5, 0.75, 1.0` when `roundness.type == 2`).
  - Add optional `connector_crossing` and `label_overlap` diagnostics (warning severity) so `auto_fix_layout` can detect and resolve crossing/label regressions.
- **Label Placement (`routing.py:position_connector_label`):**
  - Always pass `obstacles = shapes + existing_label_boxes + existing_arrow_segments`.
  - Evaluate segment midpoints plus perpendicular offsets `±(label_h / 2 + 10.0)` and longitudinal offsets `±0.2 * length` on segments with `length >= label_w + 16.0`.
  - Pass `obstacles` from `service.py:_center_label()` as well (currently omitted).

---

## 10. Compatibility & Migration Considerations

- **100% Excalidraw v2 Compatible:** All routing hints live in `customData["routing_mode"]`; `points`, `elbowed`, `roundness`, `startBinding`, and `endBinding` remain standard Excalidraw v2 fields.
- **Legacy Scenes (No `customData.routing_mode`):**
  - `elbowed == True` -> treated as `"orthogonal"`.
  - `elbowed == False` and `roundness == {"type": 2}` and `len(points) >= 3` -> treated as `"curved"`.
  - `elbowed == False` and `len(points) == 2` -> treated as `"auto"` during `auto_fix_layout` (or `"straight"` if `locked=True`).
- **`elbowed` Parameter:** Retained on `create_connector`, `update_element`, `GraphEdge`, and `BatchOperation` as a convenience alias (`elbowed=True` -> `"orthogonal"`).

---

## 11. Detailed Test Matrix (12+ Required Scenarios)

| # | Scenario | Expected Routing Decision | Key Invariants |
|---|---|---|---|
| 1 | Two nearby aligned nodes, no obstacles | `straight` (0 bends) | `len(points) == 2`, `elbowed == False`, `0` collisions |
| 2 | Two distant diagonal nodes, no obstacles (`freeform`) | `straight` diagonal | `len(points) == 2`, endpoints on `boundary_point`, `0` collisions |
| 3 | Two nodes with intervening obstacle (`auto`) | `orthogonal` detour | `elbowed == True`, `len(points) >= 4`, clearance `>= 15.0` px |
| 4 | Multiple connections between same nodes (2-3 edges) | Symmetric parallel lanes (`straight` or `curved` or `orthogonal`) | Min segment separation `>= 20.0` px, distinct labels |
| 5 | Dense architecture diagram with crossing relationships | `orthogonal` with short-to-long ordering | Minimal crossings, `0` node/header collisions |
| 6 | Sequential pipeline with skip-rank edge | Direct edges `straight`; skip edge `orthogonal` | Skip edge clears intermediate nodes by `>= 15.0` px |
| 7 | Hierarchical layered / clustered diagram | Intra-rank/cross-cluster `orthogonal`, aligned `straight` | `0` frame header (`y..y+28`) intersections |
| 8 | Node moved after connectors created (blocking straight path) | Incident & newly-blocked `"auto"` arrows reroute | `0` collisions post-move; `"straight"`-pinned arrows stay 2-pt |
| 9 | New node inserted into existing `"auto"` connector path | Affected `"auto"` connector upgrades to `orthogonal` | Unaffected connectors remain untouched |
| 10 | Mixed diagram (`straight` + `orthogonal` + `curved`) | Each connector honors its own `routing_mode` across `auto_fix` | `auto_fix` never converts `"straight"` to `elbowed=True` |
| 11 | Long connectors with labels near obstacles/other labels | Label placed on clearest long segment/offset | `0` label-shape and label-label overlaps |
| 12 | Multiple connectors competing for same face/corridor | Fan-in/fan-out face distribution + collinear overlap penalty | Distinct ports on shared face, `0` overlapping parallel lines |
| 13 | Locked connector under obstacle | Skipped by router & `auto_fix` | `points`, `x`, `y` byte-identical; unlocked arrows route around |

---

## 12. Performance Considerations

- **Context Construction:** Building `SceneRoutingContext` once per `draw_graph` / `reroute_scene_arrows` / `auto_fix_layout` call is `O(V + E)` (~1–2 ms for 200 nodes, 500 edges).
- **Grid Size in A\*:** Limiting `xs`/`ys` to obstacle edges, frame edges, and corridor midpoints keeps grid size `<= 4V`, and integer-indexed `(xi, yi)` A* runs in `< 1 ms` per edge for typical diagrams (`V <= 100`).
- **Spatial Pruning:** For `los_clear` and `crossing` checks, precompute `(min_x, min_y, max_x, max_y)` AABBs per obstacle and per existing arrow segment so non-overlapping elements are skipped in `O(1)` before Liang-Barsky / segment-segment math.
- **Selective Re-routing on Move:** When a single node moves, only re-evaluate incident arrows + straight arrows whose AABB overlaps the node's old or new AABB.

---

## 13. Implementation Phases & Priorities

1. **Phase 1 — Policy & Context Foundation (P0):**
   - Add `RoutingMode` to `contracts.py`, persist `customData["routing_mode"]`, update `reroute_scene_arrows` to respect `"straight"` vs `"orthogonal"` vs `"auto"` (no more forced `elbowed=True` on `"straight"` arrows).
   - Build `SceneRoutingContext` (obstacles, frame headers, existing segments, label boxes, structure classifier).
2. **Phase 2 — Scene-Aware Decision Tree & Multi-Criteria A\* (P1):**
   - Implement `SceneRouter` (`los_clear`, crossing/overlap/frame-header/label costs, short-to-long edge ordering, fan-in/fan-out port distribution).
   - Wire `SceneRouter` into `connect`, `batch_mutate("connect")`, `draw_graph`, `draw_mermaid`, `update_element(routing_mode=...)`, and `_apply_move`/`_apply_resize` (including non-incident blocked `"auto"` arrows).
3. **Phase 3 — Label Placement & `auto_fix_layout` Integration (P1):**
   - Upgrade `position_connector_label` to avoid shapes, sibling labels, and arrow segments with normal/longitudinal offsets; pass `obstacles` from `_center_label`.
   - Expose `routing_mode` in `inspect_scene` summaries/descriptions.
4. **Phase 4 — Curved Connectors (`routing_mode="curved"`) & Renderers (P2):**
   - Implement curved waypoint generation (`roundness={"type": 2}`) in `SceneRouter`.
   - Add Catmull-Rom / cubic Bezier rendering and endpoint-tangent arrowheads to `renderer.py` and `svg_renderer.py`.
5. **Phase 5 — Test Matrix & Benchmarks (P2):**
   - Implement all 13 test scenarios from Section 11 plus 200-node/500-edge latency benchmarks.
