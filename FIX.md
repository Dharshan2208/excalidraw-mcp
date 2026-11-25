# Excalidraw MCP — Deep Technical Audit & Remediation Plan (`FIX.md`)

**Repository:** `excalidraw-mcp` (`v0.4.0`)  
**Audit Scope:** MCP Tool Schemas & API Reliability, Computational Geometry (Arrows, Text & Layout), Scene Engine Architecture, Export Fidelity (`.excalidraw` / PNG / SVG), and Test Coverage  
**Baseline Test Run:** `uv run pytest -q` -> **551 passed, 1 skipped, 87 subtests passed** (24.01s).  
**Unverified Locally:** `ruff`, `mypy`, live browser WebSocket runtime (`live_server`), and network `excalidraw.com` sharing (`export_to_excalidraw_url`) were not executed in this read-only audit.

---

## 1. Executive Summary

`excalidraw-mcp` is a well-structured, backend-only Python MCP server (~16,320 LOC across 33 modules) that generates, edits, diagnoses, repairs, and exports Excalidraw diagrams without requiring a browser or Node.js runtime. Its core differentiators—transactional `SceneState` with rollback, bundled `Excalifont-Regular.ttf` font metrics, obstacle-aware Manhattan A* routing, 5-phase `auto_fix_layout`, and dual PNG/SVG/Excalidraw export—are strong foundations.

However, our code-level audit uncovered **several critical correctness bugs** and **architectural drift** that directly cause unreliable arrow routing, broken text containment/alignment, non-atomic tool mutations, and export discrepancies:

1. **Loop-variable shadowing in `auto_fix.py` (`BUG-001`, Critical):** Both `diagnose_layout_issues()` and `apply_layout_repairs()` look up `bound_t = bound_map.get(sid)` for each shape, then mistakenly pass the leftover `texts` loop variable `t` (always the *last* text element in the scene) to `measure_shape_text_containment()` and `_safe_wrap_and_measure()`. Every shape is checked and resized against the wrong label, and the last text element is overwritten onto every resized shape's center.
2. **Scoped repair status mismatch in `auto_fix.py` (`BUG-002`, High):** `auto_fix_scene_layout()` maps `"overlaps": {"shape_overlap"}` and `"spacing": {"crowded_spacing"}`, whereas `diagnose_layout_issues()` emits `"node_overlap"` and `"inconsistent_spacing"`. Scoped repairs for `overlaps` and `spacing` falsely report `"status": "repaired"` even when severe defects remain.
3. **Opaque & divergent `batch_mutate` (`BUG-003`, Critical):** `server.py` types `operations: list[dict[str, Any]]` instead of `BatchOperation`, hiding all 20 actions from LLM tool schemas. Worse, `SceneService.batch_mutate()` (>1,000 LOC) re-implements CRUD/connect/update independently of `SceneService` methods—omitting orthogonal routing for `connect(elbowed=True)`, dropping `font_family`/`font_size`/`arrowheads`/`roundness`, skipping frame type validation, and using naive `0.6 * fontSize` text sizing.
4. **Non-atomic `update_element` & `generate_diagram(format="architecture")` (`BUG-004`, High):** `server.py:update_element` executes up to 3 separate `SceneState.apply` transactions (`resize` -> `move` -> `update_element`), leaving partial mutations on failure and creating up to 3 undo checkpoints. `draw_architecture` similarly commits twice (`draw_graph` + `resolve_layout`).
5. **Arrow routing & endpoint defects (`BUG-005`..`BUG-009`, High):**
   - `route_orthogonal_connector()` rejects all candidate faces and falls back to a straight line through obstacles whenever any third shape is within `2 * clearance` (30px) of `source` or `target`, and excludes `source`/`target` from `obs_boxes` so A* can route through their interiors.
   - `draw_graph()` and `batch_mutate("connect")` store 2-point straight arrows even when `elbowed=True`, deferring routing to render time (where `reroute_scene_arrows` lane spacing and label placement are skipped).
   - `draw_graph()` shifts parallel straight edges along the center-to-center normal without re-projecting onto ellipse/diamond boundaries.
   - `reroute_scene_arrows()` ignores its `only_elbowed` parameter, collapses parallel lanes onto shared A* corridors, and `get_shape_port()` clamps ports outside rectangles when `width < 20` or `height < 20`.
   - `_move_arrow_endpoints()` and `_reroute_connector()` raise `SceneError` instead of rerouting when moving/resizing shapes attached to `elbowed=True` connectors.
6. **Text measurement, wrapping & export divergence (`BUG-010`..`BUG-015`, High):**
   - `elements.text()` uses `max(map(len, lines)) * fs * 0.6` instead of `fonts.measure_text_dimensions()`, corrupting `add_text()`, `connect()`, `draw_graph()`, and `_shape_elements()` (which measures with `measure_text_dimensions` and then discards the result when calling `text()`).
   - `wrap_text_to_shape()` clamps `max_chars = max(20, ...)` (overflowing shapes narrower than ~20 chars) and wraps by character count instead of pixel width.
   - `text_padding.py` and `layout.py:shape_dimensions()` use a `1.6` / `1.65` multiplier for diamonds instead of the geometric `w/W + h/H <= 1` constraint (which requires `>= 2.0` when `w/W == h/H`), and force all ellipses to circles (`w == h`).
   - `svg_renderer.py` ignores `t["x"], t["y"]` for multi-point arrow labels (always placing them at the chord midpoint), ignores `textAlign` on standalone text, and uses `0.6 * font_size` for label background masks.
   - Neither `renderer.py` nor `svg_renderer.py` applies `angle` rotation when drawing elements, while `_compute_bounds()` rotates arrow points around `(x + w/2, y + h/2)` even though `x, y` is `world_pts[0]` rather than `min_x, min_y`.

---

## 2. Overall Repository Health Assessment

| Dimension | Rating | Summary |
| :--- | :--- | :--- |
| **Core Architecture & State Safety** | **Strong** | `SceneState` (`RLock`, re-entrancy guard, `deepcopy` draft isolation, `normalize_document` + `normalize_relationships`, bounded undo) and POSIX `dir_fd`/`O_NOFOLLOW` persistence in `scene.py` are solid. |
| **Existing Strengths Worth Preserving** | **Strong** | Zero-browser Pillow+Pygments+Excalifont stack, lossless PNG JSON embedding, 45%+ token savings via `core`/`full` toolsets, Sugiyama/clustered layouts, Mermaid/DSL parsers, AES-GCM sharing. |
| **MCP Tool Surface & LLM Ergonomics** | **Needs Work** | 21 tools (`12 core`, `9 full`) with duplicated capabilities (`export_to_excalidraw_url`, `read_diagram_guide`), opaque `batch_mutate` dict schema, silent parameter drops in `generate_diagram`, and `skills.py` prompts referencing `full`-only tools in `core` mode. |
| **Computational Geometry (Text & Arrows)** | **Fragile** | Critical `t` vs `bound_t` shadowing in `auto_fix.py`, unmeasured `0.6 * fs` text widths in `elements.py`, diamond/ellipse sizing math gaps, A* stub-collision fallback, and missing `elbowed` routing in `draw_graph`/`batch_mutate`. |
| **Export Consistency (JSON / PNG / SVG)** | **Moderate** | PNG and SVG diverge on multi-point arrow labels, text alignment, code block line heights, and font scaling; neither renders `angle` rotation or non-solid `fillStyle`. |
| **Maintainability** | **Needs Work** | `service.py` (3,819 LOC) duplicates mutation logic inside `batch_mutate` (>1,000 LOC) and duplicates file-export hardening across PNG/SVG/Obsidian. |
| **Test Suite** | **Good Breadth, Key Gaps** | 551 passing tests (+87 subtests), but missing multi-label `auto_fix` regression tests, `batch_mutate` vs `SceneService` parity tests, PNG vs SVG cross-renderer parity tests, and property-based/stress tests. |

### Evaluation of Core Differentiating Capabilities

| Capability | What Works Well | Limitations / Unreliable Results | Precision & Determinism Plan | Disposition |
| :--- | :--- | :--- | :--- | :--- |
| **Backend-only Scene Generation** | Zero browser/Node dependency; clean `models.py` & `document.py` contract. | `elements.text()` uses `0.6 * fs` heuristic; `SceneState` deepcopies entire doc on every op. | Replace heuristic with `measure_text_dimensions()`; keep `SceneState` contract intact. | **Retain & Improve** |
| **Mermaid Generation (`mermaid.py`)** | Parses `flowchart`/`graph`, subgraphs, shapes, edge labels, `&` chains. | `generate_diagram` drops style params; no `sequenceDiagram`/`erDiagram` yet; cycles fail unless `cycle_fallback=True`. | Forward `style` kwargs; document supported subset clearly. | **Retain & Improve** |
| **Architecture Generation (`parser.py`, `layout.py`)** | Tiered `architectural_layout` + `clustered_layout` with frames. | `draw_architecture` is 2 undo steps; `resolve_scene_layout` uses hardcoded magic coordinates (`fx > 1600`). | Merge into single `SceneState.replace`; replace magic coords with topology-driven frame layout. | **Improve** |
| **Programmatic Editing (`update_element`, `batch_mutate`)** | `ref_map` symbolic IDs in `batch_mutate`; cascading `delete` & `move`. | Non-atomic `update_element`; `batch_mutate` drifts from `SceneService`; double-translation on grouped/framed labels. | Share internal mutation helpers; make `update_element` 1 transaction; expose `BatchOperation` schema. | **Redesign Internals, Keep API** |
| **Font-Aware Text Containment (`fonts.py`, `text_padding.py`)** | Bundled `Excalifont-Regular.ttf`; `fc-list` + Latin glyph check. | `max_chars >= 20` clamp; diamond `1.6x` under-sizes; `auto_fix.py` `t` vs `bound_t` bug. | Pixel-width greedy wrapping; exact `w/W + h/H <= 1` diamond formula; fix `bound_t` bug. | **Improve** |
| **Obstacle-Aware Routing (`routing.py`)** | Sparse corridor A* + `position_connector_label` + multi-edge slot offsets. | `stub_s`/`stub_e` collision aborts to straight line; `source`/`target` not obstacles; `only_elbowed` dead; `draw_graph`/`batch_mutate` skip it. | Adaptive stub/escape ports; include `source`/`target` boxes for interior segments; lane-aware A* costs. | **Improve** |
| **Geometry Diagnostics & Auto-Fix (`auto_fix.py`)** | 5-phase pipeline with rollback on new severe defects. | `t` vs `bound_t` bug; `scope_type_map` mismatch; `code_block` not excluded; stale `y1_max` in sweep. | Fix `bound_t`, `scope_type_map`, `code_block` filter, and re-sort/update bounds in overlap loop. | **Improve** |
| **PNG / SVG / `.excalidraw` Export** | Lossless JSON in PNG `tEXt`; SVG XSS escaping; `dir_fd` in `scene.py`. | SVG misplaces multi-point arrow labels; neither renders `angle` or `fillStyle`; exports lack `dir_fd`/`os.link`. | Unify geometry/label placement across PNG & SVG; extract shared atomic file writer. | **Improve** |
| **Core / Full Toolset Organization** | 12 `core` vs 21 `full` tools (~45% token savings). | `skills.py` prompts reference `full`-only tools; 2 duplicate tools in `full`. | Remove duplicate tools; align `skills.py` prompts with active toolset. | **Retain & Refine** |

---

## 3. Complete MCP Tool Inventory & Reliability Classification

Verified against `create_server(toolset="full")` in [server.py](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/excalidraw_mcp/server.py): **21 tools** total (**12 `core`**, **9 `full`-only**).

| Tool | Toolset | Classification | Primary Issues Identified |
| :--- | :--- | :--- | :--- |
| `clear` | `core` | **Reliable and well-designed** | None. Clean 0-arg reset with accurate annotations. |
| `delete` | `core` | **Reliable and well-designed** | None. Clean cascade & lock checks. |
| `undo` | `core` | **Reliable and well-designed** | Affected externally by multi-commit `update_element` / `draw_architecture`. |
| `preview` | `core` | **Reliable and well-designed** | Minor: dead `max_dimension is not None` check (`server.py:624`); inherits renderer bugs. |
| `create_shape` | `core` | **Functional (Precision)** | No `frame_id` validation; `w`/`h` vs `width`/`height` mismatch; `Color` regex mismatch; doesn't return expanded `width`/`height`. |
| `create_connector` | `core` | **Functional (Precision)** | Optional dual-mode args; silently ignores coords when IDs given; unused `backgroundColor`/`roundness`; `elbowed=True` blocks later `move`/`resize`. |
| `add_frame` | `core` | **Functional (Precision)** | No validation rejecting bound labels (`containerId`) or nested frames in `element_ids`. |
| `add_text` | `core` | **Functional (Precision)** | No `frame_id` validation; uses naive `0.6 * fontSize` width instead of `measure_text_dimensions()`. |
| `auto_fix_layout` | `core` | **Functional (Precision)** | `min_gap` lacks Pydantic bounds; `name` accesses disk in `core`; critical internal bugs in `auto_fix.py` (`t` vs `bound_t`, `scope_type_map`). |
| `export_png` | `full` | **Functional (Precision)** | `SceneName` rejects `.` so `.png` stripping in `service.py:997-998` is unreachable. |
| `export_svg` | `full` | **Functional (Precision)** | `SceneName` rejects `.` so `.svg` stripping in `service.py:1108-1109` is unreachable. |
| `set_viewport` | `full` | **Functional (Precision)** | `zoom` unbounded in schema; `Color` regex mismatch; non-atomic when `focus_element_ids` + overrides combined; no-op bumps revision. |
| `update_element` | `core` | **Unreliable / Inconsistent** | Non-atomic 3-step execution (`resize` -> `move` -> `update_element`); 3 undo steps; fails on `elbowed=True` attached shapes. |
| `batch_mutate` | `core` | **Unreliable / Inconsistent** | Opaque `list[dict[str, Any]]` schema; re-implements & drifts from `SceneService` (drops `elbowed` routing, fonts, arrowheads, wrapping). |
| `generate_diagram` | `full` | **Unreliable / Inconsistent** | Silently drops style params in `graph`/`mermaid` modes; `architecture` mode creates 2 undo steps; doesn't document full-scene replacement. |
| `inspect_scene` | `core` | **Redundant / Complicated** | 8-mode mega-tool; exposes `live_server` in `core`; overlaps MCP resources; `find` lacks `offset`/`has_more`. |
| `scene_storage` | `full` | **Redundant / Complicated** | 6-action mega-tool; `share_url` duplicates `export_to_excalidraw_url`; `save` silently ignores `directory` for `excalidraw` format. |
| `manage_element_state` | `full` | **Redundant / Complicated** | 5-action mega-tool; `ungroup(group_id="missing")` silently succeeds; inconsistent validation between actions. |
| `export_to_excalidraw_url` | `full` | **Redundant / Complicated** | Exact duplicate of `scene_storage(action="share_url", name=...)`. |
| `read_diagram_guide` | `full` | **Redundant / Complicated** | Duplicates `excalidraw://guide/{topic}` resource; `topic` lacks enum; cites removed tool names (`group_elements`, `connect`). |
| `live_server` | `full` | **Redundant / Complicated** | `port` lacks `1..65535` bounds; `host`/`port` silently ignored on `stop`/`already_running`; status lives in `inspect_scene`. |

### Missing Capabilities (High-Impact Without Bloating Tool Count)
1. **Typed `BatchOperation` schema on `batch_mutate`** (discriminated union or typed `BatchOperation` list so LLMs can discover `add_code_block`, `connect`, `move`, etc.).
2. **Standalone `add_code_block` exposure** (currently only reachable via undocumented `batch_mutate` action).
3. **Toolset-aware `skills.py` prompts** (or promoting `export_png` / `scene_storage` to `core`, since all 5 prompts currently instruct `core` agents to call `scene_storage` and `export_png`).
4. **Session switching/resetting** (`SceneService` implements `list_sessions`, `switch_session`, `reset_session`, but no MCP tool exposes them).

---

## 4. Detailed Analysis of Problematic Tools

### `BUG-003` — `batch_mutate` Opaque Schema & Behavioral Drift
- **Severity:** Critical
- **Affected tools:** `batch_mutate`
- **Relevant files & functions:**
  - `excalidraw_mcp/server.py`: `create_server.<locals>.batch_mutate` (lines 495–502)
  - `excalidraw_mcp/contracts.py`: `BatchOperation` (lines 158–227)
  - `excalidraw_mcp/service.py`: `SceneService.batch_mutate` (lines 1709–2744)
- **Exact technical explanation:**
  1. `server.py:496` declares `operations: list[dict[str, Any]]`, discarding `contracts.BatchOperation` from the MCP JSON Schema. LLMs cannot see valid `action` names or per-action parameters.
  2. `service.py:1709–2744` duplicates every mutation instead of calling shared helpers:
     - `action == "connect"` (lines 2038–2054) calls `boundary_point()` + `arrow()` directly without `route_orthogonal_connector()` even when `elbowed=True`, and drops `roundness`, `startArrowhead`, `endArrowhead`, `font_family`, `font_size`, and `backgroundColor`.
     - `action == "update_element"` (lines 2390–2415) computes `width = max(map(len, lines)) * fontSize * 0.6` without `measure_text_dimensions()`, wrapping, or container expansion, and skips `type == "frame"` validation when setting `frame_id` (lines 2284–2285).
     - `action in ("add_rectangle", "add_circle", "add_diamond")` (lines 1774–1789) omit `font_family`/`font_size` from `style`.
     - `action == "delete"` (line 2448) checks `el.get("frameId") == eid` instead of `in removed`.
     - `action == "auto_fix_layout"` (line 2724) rebuilds `index` without filtering `isDeleted` tombstones.
- **Reproduction scenario:** Call `batch_mutate([{"action": "connect", "source_id": a, "target_id": b, "elbowed": True}])` with an obstacle shape between `a` and `b`. The stored arrow has only 2 points (`[[0,0],[dx,dy]]`) instead of an obstacle-avoiding polyline.
- **Recommended solution:** Extract internal per-document mutation helpers (`_apply_shape`, `_apply_connect`, `_apply_update`, `_apply_move`, `_apply_resize`, `_apply_delete`) used by both `SceneService` methods and `batch_mutate`. Type `operations` in `server.py` using `BatchOperation` (or a Pydantic discriminated union on `action`).
- **Tests required:** Parity test suite comparing `batch_mutate` outputs against `create_shape`, `create_connector(elbowed=True)`, `add_text`, `update_element` (wrapping + frame validation), and `delete` (frame cascade).
- **Expected outcome:** 100% behavioral parity between batch and single-tool calls, and self-documenting MCP schema for `batch_mutate`.

### `BUG-004` — Non-Atomic `update_element` & `generate_diagram(format="architecture")`
- **Severity:** High
- **Affected tools:** `update_element`, `generate_diagram`, `undo`
- **Relevant files & functions:**
  - `excalidraw_mcp/server.py`: `create_server.<locals>.update_element` (lines 416–492), `generate_diagram` (lines 809–826)
  - `excalidraw_mcp/service.py`: `SceneService.resize` (455–490), `SceneService.move` (369–453), `SceneService.update_element` (492–825), `SceneService.draw_architecture` (1378–1423)
- **Exact technical explanation:** `server.py:438–491` invokes `service.resize`, `service.move`, and `service.update_element` sequentially, each running `self.state.apply(...)`. Similarly, `draw_architecture` calls `self.draw_graph(...)` (commit 1) followed by `self.resolve_layout(...)` (commit 2).
- **Reproduction scenario:** Call `update_element(element_id=id, width=200, height=100, x=50, y=50, frame_id="bad_id")`. `ToolError` is raised, yet the element remains resized and moved in the scene. Call `generate_diagram(format="architecture", prompt="API -> DB")` then `undo()`: `resolve_layout` is undone, leaving the un-resolved graph.
- **Recommended solution:** Add optional `x`, `y`, `width`, `height` parameters to `SceneService.update_element` and execute resize -> move -> label/style update inside a single `self.state.apply(...)`. In `draw_architecture`, apply `resolve_scene_layout` to the generated document before `state.replace`.
- **Tests required:** Atomicity test asserting revision and element state are unchanged when `update_element` fails on the final step; single-`undo()` test for both `update_element` and `generate_diagram(format="architecture")`.
- **Expected outcome:** All-or-nothing execution and 1 undo step per tool invocation.

### `BUG-016` — `generate_diagram` Silent Parameter Drops & Undocumented Replacement
- **Severity:** High
- **Affected tools:** `generate_diagram`
- **Relevant files & functions:** `excalidraw_mcp/server.py` lines 769–850; `excalidraw_mcp/service.py` `draw_graph` (2746–3038), `draw_mermaid` (3188–3214)
- **Exact technical explanation:** `server.py:831–846` does not pass `_style_kwargs(...)` to `service.draw_graph()`, and `server.py:799–806` does not pass `_style_kwargs(...)`, `font_family`, or `font_size` to `service.draw_mermaid()`. Furthermore, `generate_diagram` replaces the entire active scene via `state.replace`, which is not stated in the tool description.
- **Reproduction scenario:** Call `generate_diagram(format="graph", nodes=[...], edges=[...], strokeColor="#1971c2", backgroundColor="#e7f5ff")`. Elements are created with default `#1e1e1e` / `transparent` colors.
- **Recommended solution:** Forward `_style_kwargs(...)` as `style=style` to `draw_graph` and `draw_mermaid`; update docstring to explicitly state that the active scene is replaced.
- **Tests required:** Contract test verifying `strokeColor`, `backgroundColor`, `font_family`, `font_size` propagate in both `graph` and `mermaid` formats.
- **Expected outcome:** Style parameters work uniformly across all 3 `generate_diagram` formats.

### `BUG-017` — Schema/Validation Mismatches (`Color`, `zoom`, `min_gap`, `SceneName`, `frame_id`, `skills.py`)
- **Severity:** Medium
- **Affected tools:** `create_shape`, `add_text`, `add_frame`, `auto_fix_layout`, `export_png`, `export_svg`, `set_viewport`, `live_server`, `read_diagram_guide`
- **Relevant files & functions:**
  - `excalidraw_mcp/contracts.py`: `Color` (line 12), `SceneName` (lines 14–17)
  - `excalidraw_mcp/validation.py`: `COLOR_PATTERN` (line 6)
  - `excalidraw_mcp/server.py`: `auto_fix_layout` (510), `set_viewport` (884), `live_server` (920), `diagram_guide_resource` (591–606)
  - `excalidraw_mcp/service.py`: `add_shape` (256–266), `add_text` (279–301), `add_frame` (1425–1451), `export_png` (997–998), `export_svg` (1108–1109), `set_viewport` (3250)
  - `excalidraw_mcp/skills.py`: lines 453 and prompt instructions
  - `excalidraw_mcp/design_guide.py`: lines 83, 94
- **Exact technical explanation:**
  - `contracts.Color` (`#[0-9A-Fa-f]{3,8}`) accepts 5/7-digit hex strings that `validation.COLOR_PATTERN` (`{3}|{4}|{6}|{8}`) rejects.
  - `add_shape` and `add_text` do not validate `frame_id` exists and has `type == "frame"`.
  - `add_frame` does not reject bound text (`containerId != None`) in `element_ids`.
  - `export_png` / `export_svg` use `SceneName` (forbids `.`), making `.png`/`.svg` stripping in `service.py` dead code.
  - `set_viewport.zoom`, `auto_fix_layout.min_gap`, and `live_server.port` lack Pydantic range constraints in `server.py`.
  - `skills.py` instructs `core` agents to call `scene_storage`/`export_png` (`full`-only) and uses `width=`/`height=` instead of `w=`/`h=` for `create_shape`. `design_guide.py` cites removed tools (`group_elements`, `connect`).
- **Recommended solution:** Unify `contracts.Color` with `validation.COLOR_PATTERN`; add Pydantic bounds for `zoom`, `min_gap`, `port`; validate `frame_id` in `add_shape`/`add_text`; reject bound labels in `add_frame`; update `skills.py` and `design_guide.py`.
- **Tests required:** Schema boundary tests for 5-digit hex, `zoom <= 0`, `min_gap < 0`, `port > 65535`, invalid `frame_id` in `create_shape`/`add_text`.

---

## 5. Arrow Placement & Routing Root-Cause Analysis

### `BUG-005` — A* Stub-Collision Fallback & Source/Target Interior Routing
- **Severity:** High
- **Affected tools:** `create_connector`, `auto_fix_layout`, `preview`, `export_png`, `export_svg`
- **Relevant files & functions:** `excalidraw_mcp/routing.py`: `route_orthogonal_connector()` (lines 197–356)
- **Exact technical explanation:**
  1. `obs_boxes` inflates every non-source/target shape by `clearance=15.0` (line 223). `stub_s` and `stub_e` extend `15.0` outward from `source` and `target` (lines 257–258). If any obstacle shape is within `2 * clearance` (`30.0px`) of `source` or `target`, `seg_hits_obs(p_start, stub_s)` or `seg_hits_obs(stub_e, p_end)` returns `True` (lines 260–261), rejecting **all** candidate face pairs and falling back to `[p_start, p_end]` (lines 352–355)—a straight line that cuts directly through obstacles.
  2. Lines 217–218 exclude `source_id` and `target_id` from `obs_boxes` completely. Once A* leaves `stub_s`, segments can route directly back through the interior of `source` or `target`.
  3. Line 310 (`if (cx, cy) == target_pt:`) uses exact float equality, and lines 320–321 (`all_x.index(cx)`) perform linear scans inside the A* loop.
- **Reproduction scenario:** Place `A(100,100,100x60)`, `B(100,300,100x60)`, `C(100,180,100x60)` (20px gap below `A`). Call `route_orthogonal_connector(A, B, [A, B, C], clearance=15.0)`. All stubs on `A`'s bottom face collide with `C`'s inflated box.
- **Recommended solution:**
  1. Reduce stub clearance dynamically (e.g. `min(clearance, gap / 2.0)`) or allow zero-stub exit when an obstacle is within `2 * clearance`, checking only the *uninflated* obstacle body for hard collision.
  2. Include `source` and `target` uninflated bounding boxes in A* obstacle checks for all segments after `stub_s` and before `stub_e`.
  3. Index `all_x` / `all_y` by integer grid indices `(xi, yi)` instead of float tuples and `list.index()`.
- **Tests required:** Unit test with 20px obstacle gap (`clearance=15.0`) asserting 0 collisions against `A`, `B`, and `C`.

### `BUG-006` — `choose_natural_faces()` Wrong Priority on Diagonal Offsets
- **Severity:** Medium
- **Affected tools:** `create_connector`, `auto_fix_layout`, `preview`, `export_png`, `export_svg`
- **Relevant files & functions:** `excalidraw_mcp/routing.py`: `choose_natural_faces()` (lines 87–136)
- **Exact technical explanation:** `if ty >= sy + sh - 5.0:` (line 110) triggers whenever `target` is at least `sh - 5` below `source`, even if `dx = 500` and `dy = 65`. It returns `[("bottom", "top"), ("right", "top"), ("bottom", "left")]`—omitting `("right", "left")` completely.
- **Reproduction scenario:** `source=(100, 100, 100x60)`, `target=(500, 156, 100x60)`. `choose_natural_faces` never considers `("right", "left")`.
- **Recommended solution:** Rank candidate face pairs by dominant axis (`abs(dx) / max(sw, 1)` vs `abs(dy) / max(sh, 1)`) and include all 4 natural pairs ordered by alignment score rather than hard-thresholding on `5.0px`.
- **Tests required:** Unit test for wide-diagonal layout verifying `("right", "left")` is ranked first when `dx >> dy`.

### `BUG-007` — `reroute_scene_arrows()` Dead `only_elbowed`, Lane Collapse & Narrow-Shape Clamping
- **Severity:** High
- **Affected tools:** `auto_fix_layout`, `create_connector`, `update_element`
- **Relevant files & functions:** `excalidraw_mcp/routing.py`: `reroute_scene_arrows()` (lines 418–513), `get_shape_port()` (lines 14–85)
- **Exact technical explanation:**
  1. `only_elbowed: bool = False` (line 422) is never referenced in `reroute_scene_arrows()`.
  2. Non-colliding straight arrows (`elbowed=False`) are overwritten with `get_shape_port(source_el, default_s_face, slot_offset)` (lines 465–466, 492), destroying `boundary_point` diagonal attachment and ignoring `angle`.
  3. Parallel arrows between the same pair receive `slot_offset` only at `p_start`/`p_end`/`stub_s`/`stub_e`; A* has no lane-separation cost, so parallel routes merge onto identical obstacle-boundary lines.
  4. `get_shape_port()` lines 72–81 clamp rectangle ports with `max(x + 10.0, min(x + w - 10.0, cx + offset))`. If `w < 20.0`, `x + 10.0 > x + w - 10.0`, placing the port **outside** the shape.
- **Reproduction scenario:** Create a `16x16` rectangle and call `get_shape_port(rect, "top", 0.0)` -> returns `x + 10.0` (outside `[x, x + 16]`? No, `min(x + 6, cx)` = `x + 6`, then `max(x + 10, x + 6)` = `x + 10`, which for `w=12` is `x + 10` vs `x + 12`, and for `w=8` is `x + 10 > x + 8`!).
- **Recommended solution:** Honor `only_elbowed`; preserve `boundary_point()` for non-colliding straight arrows; clamp rectangle port margin to `min(10.0, w * 0.25)` (and `h * 0.25`); add a small penalty in A* for reusing segments already occupied by another arrow in the scene.
- **Tests required:** Unit tests for `w=8` port bounds, `only_elbowed=True` preservation of straight arrows, and 2-lane parallel detour separation.

### `BUG-008` — `draw_graph()` & `batch_mutate("connect")` Skip Orthogonal Routing & Misplace Parallel Endpoints
- **Severity:** High
- **Affected tools:** `generate_diagram(format="graph"|"mermaid"|"architecture")`, `batch_mutate`
- **Relevant files & functions:**
  - `excalidraw_mcp/service.py`: `draw_graph()` (lines 2942–2989), `batch_mutate()` (`connect`, lines 2038–2054)
- **Exact technical explanation:**
  1. Neither `draw_graph()` nor `batch_mutate("connect")` calls `route_orthogonal_connector()` when `elbowed=True`. They emit 2-point straight arrows `[[0, 0], [dx, dy]]`, leaving `.excalidraw` JSON and `check_diagram_geometry()` with unrouted diagonal segments while `renderer.py` / `svg_renderer.py` re-route them on the fly (without lane offsets or label updates).
  2. `draw_graph()` lines 2971–2972 offset parallel straight edges by adding `(nx * offset_mag, ny * offset_mag)` to `boundary_point()`. On ellipses and diamonds, a tangential shift moves endpoints **off the perimeter**.
  3. `draw_graph()` lines 2975–2985 omit `startArrowhead` and `endArrowhead` when copying edge style keys into `edge_style`, silently dropping `GraphEdge.startArrowhead`/`endArrowhead`!
- **Reproduction scenario:** Call `generate_diagram(format="graph", nodes=[...], edges=[{"source": "a", "target": "b", "elbowed": True, "endArrowhead": "diamond"}])`. The stored arrow has 2 points and `endArrowhead: "arrow"`.
- **Recommended solution:** Route `elbowed=True` edges (and colliding edges) via `routing.reroute_scene_arrows()` inside `draw_graph()` and `batch_mutate("connect")`; compute parallel straight edge endpoints by offsetting the target/ray or using `get_shape_port()` on the shape boundary; copy `startArrowhead`/`endArrowhead` into `edge_style`.
- **Tests required:** Assert `points` length > 2 for elbowed graph edges with obstacles, `endArrowhead == "diamond"` preserved, and parallel ellipse endpoints satisfy `(px-cx)^2/rx^2 + (py-cy)^2/ry^2 ≈ 1`.

### `BUG-009` — Moving/Resizing Shapes Attached to Elbowed Connectors Fails
- **Severity:** High
- **Affected tools:** `update_element`, `batch_mutate`
- **Relevant files & functions:** `excalidraw_mcp/service.py`: `_reroute_connector()` (lines 160–180), `_move_arrow_endpoints()` (lines 183–201), `move()` (line 385)
- **Exact technical explanation:** Both `_reroute_connector` and `_move_arrow_endpoints` raise `SceneError("...attached to elbowed or rotated arrows is not supported yet")` whenever an attached arrow has `elbowed=True`.
- **Reproduction scenario:** Create two shapes, connect them with `create_connector(..., elbowed=True)`, then call `update_element(element_id=shape_a, x=300)`. Fails with `ToolError`.
- **Recommended solution:** When `elbowed=True` and a bound endpoint moves or a bound shape resizes, re-run `route_orthogonal_connector(source, target, obstacles=...)` and reposition the arrow's bound label.
- **Tests required:** Move and resize shapes connected by an `elbowed=True` arrow and verify updated `points`, `x`, `y`, and zero obstacle collisions.

---

## 6. Text Placement & Measurement Root-Cause Analysis

### `BUG-001` — Loop-Variable Shadowing (`t` instead of `bound_t`) in `auto_fix.py`
- **Severity:** Critical
- **Affected tools:** `auto_fix_layout`
- **Relevant files & functions:** `excalidraw_mcp/auto_fix.py`: `diagnose_layout_issues()` (lines 362–410) and `apply_layout_repairs()` (lines 1189–1256)
- **Exact technical explanation:** Both functions iterate `for t in texts:` to build `bound_map`, leaving `t` bound to `texts[-1]`. Inside `for s in shapes:`, they look up `bound_t = bound_map.get(sid)` and check `bound_t.get("text")`, but then pass **`t`** (not `bound_t`) to `measure_shape_text_containment(s, t)` and `_safe_wrap_and_measure(s, t, ...)`, and in `apply_layout_repairs` mutate `t["x"], t["y"], t["width"], t["height"]` instead of `bound_t`. Furthermore, line 1251 computes `wrapped` without assigning `bound_t["text"] = wrapped`.
- **Reproduction scenario:** Create `R1(100x50)` with label `"This is a very long overflowing label"` and `R2(250x120)` with label `"OK"`. Run `auto_fix_layout(dry_run=True)`. `diagnose_layout_issues()` reports **0** `text_clipping` issues because `R1` was measured against `R2`'s `"OK"`.
- **Recommended solution:** Replace `t` with `bound_t` on lines 397, 405, 409, 1231, 1251, 1253–1256, and assign `bound_t["text"] = bound_t["originalText"] = wrapped` when wrapping changes text.
- **Tests required:** Multi-shape `diagnose_layout_issues` and `apply_layout_repairs` test with both `(long, short)` and `(short, long)` label orders, verifying each shape's own `bound_t` is measured, resized, and centered.

### `BUG-010` — Naive `0.6 * fontSize` Text Width in `elements.text()`
- **Severity:** High
- **Affected tools:** `add_text`, `create_shape`, `create_connector`, `update_element`, `batch_mutate`, `generate_diagram`
- **Relevant files & functions:** `excalidraw_mcp/elements.py`: `text()` (lines 168–170); `excalidraw_mcp/service.py`: `_shape_elements()` (79–83), `add_text()` (279–301), `connect()` (916–924), `draw_graph()` (3011–3018)
- **Exact technical explanation:** `elements.text()` sets `text_w = max(map(len, lines)) * fs * 0.6`. Even `_shape_elements()`, which calls `measure_text_dimensions()`, discards the measured `(text_w, text_h)` and calls `text()` + `_center_label()`, storing inaccurate `width`/`x`/`y` in the Excalidraw document.
- **Reproduction scenario:** `add_text(100, 100, "WWWWWWWWWW", font_size=20)` sets `width=120.0`, whereas actual `Excalifont` / `sans-serif` pixel width is significantly larger, causing `_compute_bounds` to clip the right edge of standalone text in PNG/SVG.
- **Recommended solution:** Call `fonts.measure_text_dimensions(content, font_family=ff, font_size=fs)` inside `elements.text()` (with `len * fs * 0.6` only as an exception fallback).
- **Tests required:** Assert `add_text(0, 0, "WWWWWWWWWW")["width"] > add_text(0, 0, "iiiiiiiiii")["width"]` and matches `measure_text_dimensions`.

### `BUG-011` — `wrap_text_to_shape()` `max_chars >= 20` Floor & Character-Count Wrapping
- **Severity:** High
- **Affected tools:** `create_shape`, `update_element`, `auto_fix_layout`, `generate_diagram`
- **Relevant files & functions:** `excalidraw_mcp/layout.py`: `wrap_text_to_shape()` (lines 34–72), `shape_dimensions()` (75–112)
- **Exact technical explanation:** `wrap_text_to_shape` clamps `max_chars = max(20, int(safe_w / char_w))` and wraps via `textwrap.wrap` using `'M'` width `* 0.85`. Narrow shapes (`w < 20 * char_w`) never wrap below 20 characters, and wide glyphs (CJK, uppercase, emoji) overflow pixel bounds.
- **Reproduction scenario:** `wrap_text_to_shape("ABCDEFGHIJKLMNOPQRST", shape="rectangle", target_w=100, font_size=20)` returns a single 20-char line (~240px wide) inside a 100px box.
- **Recommended solution:** Lower the floor to `max(4, ...)` and implement pixel-accurate greedy word wrapping using `font.getbbox(candidate_line)` (with character-level break for single words wider than `safe_w`).
- **Tests required:** Unit tests for narrow rectangles (`w=100`), wide uppercase strings, and CJK strings asserting `measure_text_dimensions(wrapped)[0] <= safe_w`.

### `BUG-012` — Diamond & Ellipse Containment Math in `text_padding.py` and `layout.py`
- **Severity:** High
- **Affected tools:** `create_shape`, `update_element`, `auto_fix_layout`, `generate_diagram`
- **Relevant files & functions:**
  - `excalidraw_mcp/text_padding.py`: `required_container_size()` (lines 4–12)
  - `excalidraw_mcp/layout.py`: `shape_dimensions()` (lines 97–107)
- **Exact technical explanation:**
  - A rectangle of size `(w, h)` fits inside a diamond of size `(W, H)` iff `w / W + h / H <= 1.0`. Both `text_padding.py` (`text_w * 1.6 + 48`) and `layout.py` (`text_w * 1.65 + 60`) use multipliers `< 2.0`, so for long multi-line text `w/W + h/H ≈ 1/1.6 + 1/1.6 = 1.25 > 1.0`—text corners protrude outside the diamond edges!
  - For ellipses, `text_padding.py` and `layout.py` both force `W = H = hypot(text_w, text_h) + pad`, turning wide ellipses into giant squares/circles. An ellipse `(W, H)` inscribes `(w, h)` iff `(w/W)^2 + (h/H)^2 <= 1`, e.g., `W = w * sqrt(2) + pad`, `H = h * sqrt(2) + pad`.
- **Reproduction scenario:** Create a diamond with a 4-line, 30-char-per-line label; render PNG/SVG and observe text corners intersecting the diamond's diagonal edges.
- **Recommended solution:** Use `W >= 2.0 * w + pad_w`, `H >= 2.0 * h + pad_h` for diamonds, and `W >= w * math.sqrt(2) + pad_w`, `H >= h * math.sqrt(2) + pad_h` for ellipses (preserving aspect ratio when resizing existing shapes).
- **Tests required:** Property-based/unit test verifying `text_w / W + text_h / H <= 1.0` for diamonds and `(text_w / W)^2 + (text_h / H)^2 <= 1.0` for ellipses across varied text aspect ratios.

### `BUG-013` — Stale `customData["fontFamily"]` on Container Font Update
- **Severity:** Medium
- **Affected tools:** `update_element`
- **Relevant files & functions:** `excalidraw_mcp/service.py`: `update_element()` (lines 744–748, 779–783)
- **Exact technical explanation:** Updating `font_family` on a shape updates `target["fontFamily"]` on its bound label, but leaves any existing `target["customData"]["fontFamily"]` untouched. `renderer.py:635` and `svg_renderer.py:463` prioritize `customData["fontFamily"]`, so the font change has no visual effect.
- **Recommended solution:** Reuse a single `_apply_font_family(text_el, font_family)` helper in both direct text updates and container updates.

### `BUG-014` — `code_block` Elements Corrupted by `auto_fix.py`
- **Severity:** High
- **Affected tools:** `auto_fix_layout`
- **Relevant files & functions:** `excalidraw_mcp/auto_fix.py`: `diagnose_layout_issues()` (line 337), `apply_layout_repairs()` (line 1182)
- **Exact technical explanation:** `auto_fix.py` filters out `code_block_header` but not `code_block` / `code-block`, causing `auto_fix_layout` to re-wrap and re-center syntax-highlighted code blocks.
- **Recommended solution:** Skip elements with `_cd(e).get("type") in ("code_block", "code-block")` in Phase 1 text containment/wrapping/centering.

---

## 7. Scene Engine & Geometry Problems

### `BUG-015` — Rotation (`angle`) Ignored in Renderers & Corrupted in `_compute_bounds()`
- **Severity:** High
- **Affected tools:** `preview`, `export_png`, `export_svg`, `auto_fix_layout`, `inspect_scene`
- **Relevant files & functions:**
  - `excalidraw_mcp/renderer.py`: `_compute_bounds()` (lines 85–128), `render_scene_image()` (lines 463–711)
  - `excalidraw_mcp/svg_renderer.py`: `render_scene_svg()` (lines 267–540)
- **Exact technical explanation:**
  1. `_compute_bounds` rotates arrow `points` around `(x + w/2, y + h/2)`. However, `routing.py:498`, `service.py:172, 198, 886` set `x, y` to `world_pts[0]`, not `min(all_x), min(all_y)`. For arrows pointing left or up, `x + w/2` is outside the arrow's true bounding box.
  2. Neither `renderer.py` nor `svg_renderer.py` applies `angle` rotation when drawing shapes, arrows, or text, causing a mismatch between `_compute_bounds` (which expands the canvas for rotation) and the drawn elements.
- **Recommended solution:** Compute arrow rotation center from the actual point-cloud bounding box `(min_x + max_x)/2, (min_y + max_y)/2`, and support `angle` rotation in SVG (`transform="rotate(...)"`) and Pillow rendering.

### `BUG-018` — `resolve_scene_layout()` Hardcoded Frame Classification & Asymmetric Spatial Claiming
- **Severity:** Medium
- **Affected tools:** `generate_diagram(format="architecture")`, `auto_fix_layout`, `batch_mutate(action="resolve_layout")`
- **Relevant files & functions:** `excalidraw_mcp/layout.py`: `resolve_scene_layout()` (lines 747–862), `check_diagram_geometry()` (642–643); `excalidraw_mcp/auto_fix.py` (515–516, 930–931)
- **Exact technical explanation:** `resolve_scene_layout()` classifies frames using magic thresholds (`fx > 1600 and fh > 800`, `fw > 2000 and fy > 1500`) and forces all other frames into a vertical stack of equal width `max_main_w`, breaking horizontal multi-frame layouts. Meanwhile, `layout.py` and `auto_fix.py` claim unframed shapes up to `100px`–`350px` below a frame (`fy + fh + 350`) as children of that frame.
- **Recommended solution:** Respect existing horizontal vs vertical frame arrangement when resolving intra-frame overlaps; restrict spatial frame claiming to shapes whose centers fall strictly inside (or within a small tolerance like `10px` of) the frame bounds.

### `BUG-019` — `auto_fix.py` Stale `y1_max` in `_resolve_node_overlaps()`
- **Severity:** Medium
- **Affected tools:** `auto_fix_layout`
- **Relevant files & functions:** `excalidraw_mcp/auto_fix.py`: `_resolve_node_overlaps()` (lines 1044–1051)
- **Exact technical explanation:** `y1_max` is computed before the inner loop, and `sorted_shapes` is mutated in-place without re-sorting, so the sweep-and-prune `break` condition can miss newly created overlaps.

### `BUG-020` — `move()` Double-Translation & Cross-Frame Arrow Detachment
- **Severity:** Medium
- **Affected tools:** `update_element`, `batch_mutate`
- **Relevant files & functions:** `excalidraw_mcp/service.py`: `move()` (lines 409–450), `batch_mutate()` (lines 2119–2176)
- **Exact technical explanation:** A bound label (`containerId` set) that also shares `groupIds` or `frameId` with the moved element is translated in `grouped_members`/`frame` children AND translated a second time in the `containerId in moved_targets` pass. Additionally, if an arrow has `frameId == moved_frame` and is bound to an external shape, translating the arrow detaches its external endpoint.
- **Recommended solution:** Deduplicate `moved_targets` before applying `_translate` (or exclude `containerId` elements from `grouped_members`/`frame` translation passes), and only translate arrows whose *both* bound endpoints are in `moved_targets` (or that are unbound).

---

## 8. Architectural Inconsistencies

### `ARCH-001` — PNG vs SVG Renderer Divergence
- **Severity:** High
- **Relevant files:** `excalidraw_mcp/renderer.py`, `excalidraw_mcp/svg_renderer.py`
- **Inconsistencies:**
  1. **Multi-point arrow labels:** `renderer.py:664–666` uses `t["x"], t["y"]` when `len(pts) > 2`, whereas `svg_renderer.py:494–498` always uses `(p0 + p1) / 2.0`.
  2. **Standalone text alignment:** `svg_renderer.py:520–540` ignores `textAlign`; `renderer.py:705` passes `align=text_align` without width-based x-offsetting.
  3. **Bound text alignment:** Both renderers hardcode center/middle alignment for shape labels, ignoring `textAlign`/`verticalAlign`.
  4. **Code block metrics:** `code_blocks.py`, `renderer.py`, and `svg_renderer.py` each use different line-height multipliers (`1.3` vs `1.35` vs `1.45`) and character widths.
  5. **Large-diagram PNG font clamp:** `renderer.py:634` + `fonts.py:288` clamp PNG font size to `>= 6px`, causing text overflow on large scaled-down scenes while SVG scales proportionally.
  6. **Render-time routing:** Both renderers re-route 2-point `elbowed=True` arrows at render time, masking missing routing in the `.excalidraw` JSON.

### `ARCH-002` — `service.py` God Object & Duplicated Export Hardening
- **Severity:** Medium
- **Relevant files:** `excalidraw_mcp/service.py` (3,819 LOC), `excalidraw_mcp/scene.py`
- **Explanation:** `service.py` duplicates all CRUD/connect/move/resize/update logic inside `batch_mutate`, and `export_png`, `export_svg`, `export_obsidian` each duplicate directory creation and atomic write logic without `scene.py`'s `dir_fd`/`O_NOFOLLOW`/`os.link` TOCTOU protections. Also `_label_for(index, eid)` performs O(N) linear scans inside loops across `service.py`.

### `ARCH-003` — `importer.py` Merge-Mode ID & File Collisions
- **Severity:** Medium
- **Relevant files:** `excalidraw_mcp/importer.py` (lines 259–321)
- **Explanation:** `existing_ids` filters out `isDeleted` tombstones, so an imported element matching a deleted element's ID is not remapped and fails `validate_document()`. `groupIds` and `files` keys are not remapped on collision.

### `ARCH-004` — Global FastMCP Monkey-Patching & Stale Capabilities Metadata
- **Severity:** Low
- **Relevant files:** `excalidraw_mcp/server.py` (lines 36, 47, 942, 984)
- **Explanation:** Mutating `Tool.convert_result` globally affects any other `FastMCP` instance in the same Python process; `mcp = create_server()` at import time freezes `EXCALIDRAW_TOOLSET`; line 942 has a stale comment (`27`/`43` vs `12`/`21`).

---

## 9. Missing Tests & Reproducible Failure Scenarios

| Test Category | Missing Scenario | Target File(s) |
| :--- | :--- | :--- |
| **Regression (`BUG-001`)** | Multi-shape `diagnose_layout_issues` & `apply_layout_repairs` with `(long, short)` and `(short, long)` bound labels. | `tests/test_auto_fix_layout.py` |
| **Regression (`BUG-002`)** | `auto_fix_layout(repair_scope="overlaps")` and `"spacing"` when `node_overlap` / `inconsistent_spacing` remain. | `tests/test_auto_fix_layout.py` |
| **Parity (`BUG-003`)** | Matrix comparing `batch_mutate` actions (`connect(elbowed=True)`, `update_element` wrapping/frame check, `add_*` fonts) vs `SceneService` methods. | `tests/test_toolset.py` / new `tests/test_batch_parity.py` |
| **Atomicity (`BUG-004`)** | `update_element` partial-failure rollback + single `undo()` for `update_element` and `generate_diagram(format="architecture")`. | `tests/test_editing_workflow.py` |
| **Geometry (`BUG-005..008`)** | 20px obstacle gap A* routing; wide-diagonal `choose_natural_faces`; `w=8` port bounds; `only_elbowed=True`; `draw_graph` `endArrowhead` & ellipse perimeter tests. | `tests/test_arrow_routing.py`, `tests/test_graph_generation.py` |
| **Text & Shapes (`BUG-010..012`)** | `"WWWW"` vs `"iiii"` width check in `add_text`; narrow (`w=100`) wrapping; diamond `w/W + h/H <= 1` and ellipse `(w/W)^2 + (h/H)^2 <= 1` invariants. | `tests/test_text_containment.py`, `tests/test_geometry_edge_cases.py` |
| **Export Parity (`ARCH-001`)** | Cross-renderer test comparing PNG vs SVG bounds, multi-point arrow label coordinates, and `textAlign` alignment. | `tests/test_svg_export.py`, `tests/test_png_export_and_code_blocks.py` |
| **State & Merge (`BUG-020`, `ARCH-003`)** | `move()` with grouped+bound labels; `import_scene(mode="merge")` with `isDeleted` tombstone IDs and colliding `files`. | `tests/test_relationship_cascades.py`, `tests/test_storage.py` |
| **Stress / Property-Based** | Hypothesis invariants on `normalize_relationships` & `required_container_size`; 1,000+ element benchmark for `apply()`, `diagnose_layout_issues()`, and A* routing. | `tests/test_architecture_scaling.py` |

---

## 10. Recommended Algorithmic Improvements

1. **Pixel-Accurate Greedy Word Wrapping (`layout.py:wrap_text_to_shape`):** Replace character-count `textwrap.wrap` + `max(20, ...)` floor with binary/greedy word wrapping measured via `font.getbbox(line)`, breaking long tokens by character only when a single word exceeds `safe_w`.
2. **Exact Inscribed Geometry (`text_padding.py`, `layout.py:shape_dimensions`):**
   - Diamond: enforce `W >= 2.0 * text_w + pad_w` and `H >= 2.0 * text_h + pad_h` (guaranteeing `text_w/W + text_h/H <= 1.0` with padding).
   - Ellipse: enforce `W >= text_w * sqrt(2) + pad_w` and `H >= text_h * sqrt(2) + pad_h` rather than forcing `W == H`.
3. **Adaptive Stub & Lane-Aware A\* Routing (`routing.py:route_orthogonal_connector`):**
   - Compute `eff_clearance = min(clearance, min_gap_to_neighbor / 2.0)` per port so tight corridors don't abort all candidate faces.
   - Add uninflated `source` and `target` rects to obstacle checks for all interior path segments (excluding `p_start -> stub_s` and `stub_e -> p_end`).
   - Index grid coordinates `(xi, yi)` as integers instead of floats; add a small segment-overlap penalty for previously routed arrows to preserve parallel lanes through detours.
   - Re-route `elbowed=True` connectors automatically in `_reroute_connector` and `_move_arrow_endpoints`.
4. **Shared Text & Bounds Geometry (`elements.py`, `renderer.py`, `svg_renderer.py`):**
   - Compute `width, height` in `elements.text()` via `measure_text_dimensions()`.
   - Eagerly route `elbowed=True` edges in `draw_graph()` and `batch_mutate("connect")` so `.excalidraw` JSON, `check_diagram_geometry()`, PNG, and SVG all share the exact same polyline and label coordinates.

---

## 11. Recommended API & Schema Improvements

1. **Expose `BatchOperation` in `batch_mutate`:** Change `operations: list[dict[str, Any]]` to `operations: list[BatchOperation]` (or a Pydantic discriminated union on `action`) so LLMs see all 20 actions and valid fields.
2. **Consolidate Redundant Tools (Reduce or Keep <= 19 Tools):**
   - Remove `export_to_excalidraw_url` (keep `scene_storage(action="share_url")`).
   - Remove `read_diagram_guide` (fix `excalidraw://guide/{topic}` resource to emit all guide fields).
   - Optionally expose `add_code_block` as a first-class tool or clearly document it via typed `BatchOperation`.
3. **Standardize Parameters & Constraints:**
   - Support `width`/`height` aliases (or document `w`/`h` consistently across `skills.py` and `design_guide.py`).
   - Unify `contracts.Color` with `validation.COLOR_PATTERN`.
   - Add Pydantic bounds to `auto_fix_layout.min_gap` (`0..1000`), `set_viewport.zoom` (`0.01..50.0`), and `live_server.port` (`1..65535`).
   - Reject mixed `source_id`/`target_id` + `x`/`y`/`x2`/`y2` in `create_connector`.
   - Forward `_style_kwargs` to `draw_graph` and `draw_mermaid` in `generate_diagram`, and document full-scene replacement.
4. **Align `skills.py` Prompts with Toolsets:** Ensure `core` mode prompts only instruct agents to use `core` tools (or promote `export_png` / `scene_storage` if workflows depend on them).

---

## 12. Backward Compatibility Considerations

- **`w`/`h` vs `width`/`height`:** Keep `w`/`h` on `create_shape` and `add_frame` (accepting `width`/`height` as optional aliases if added) so existing MCP clients do not break.
- **`update_element` return shape:** Consolidating `resize` + `move` + `update_element` into one `SceneState.apply` should preserve the merged return keys (`status`, `element_id`, `x`, `y`, `width`, `height`, `label_id`) expected by existing callers.
- **`BatchOperation` `extra="allow"`:** Keep `extra="allow"` during transition if external callers pass harmless extra metadata, while validating known fields strictly.
- **`export_png` / `export_svg` `name`:** Keep `SceneName` compatibility for extensionless names; if `.png`/`.svg` stripping is desired, widen the export name pattern rather than breaking existing names.
- **`auto_fix_layout` `verbose=False` summary:** Preserve `initial_issue_count`, `unresolved_issue_count`, `applied_change_count`, and `changed_element_ids` keys.

---

## 13. Prioritized Implementation Roadmap

### P0: Critical Correctness & Reliability Issues
1. **`BUG-001`:** Fix `t` -> `bound_t` loop-variable shadowing in `auto_fix.py` (`diagnose_layout_issues` & `apply_layout_repairs`) and persist `wrapped` text.
2. **`BUG-002`:** Fix `scope_type_map` in `auto_fix.py:1751–1757` (`"node_overlap"`, `"inconsistent_spacing"`).
3. **`BUG-003`:** Refactor `service.py` to share mutation helpers between `SceneService` and `batch_mutate`, and expose `BatchOperation` schema on `batch_mutate`.
4. **`BUG-004`:** Make `server.py:update_element` and `service.py:draw_architecture` single-transaction (`SceneState.apply` / `replace`).

### P1: Major Tool Precision Improvements
5. **`BUG-010` & `BUG-011`:** Use `measure_text_dimensions()` in `elements.text()` and pixel-accurate greedy wrapping in `wrap_text_to_shape()`.
6. **`BUG-012`:** Fix diamond (`>= 2.0x`) and ellipse (`sqrt(2)x`, aspect-preserving) sizing in `text_padding.py` and `layout.py:shape_dimensions()`.
7. **`BUG-005`, `BUG-007`, `BUG-008`, `BUG-009`:** Fix A* stub-collision fallback & source/target interior checks, honor `only_elbowed`, fix `w < 20` port clamping, route `elbowed=True` in `draw_graph()`/`batch_mutate("connect")`, copy `startArrowhead`/`endArrowhead` in `draw_graph()`, and support moving/resizing shapes bound to `elbowed=True` arrows.
8. **`BUG-013`, `BUG-014`, `BUG-016`, `BUG-017`:** Fix `customData["fontFamily"]` stale override, exclude `code_block` from `auto_fix` wrapping, forward styles in `generate_diagram`, validate `frame_id` in `add_shape`/`add_text`, and unify `Color`/`zoom`/`min_gap`/`port` validation.

### P2: Architecture & Algorithmic Improvements
9. **`ARCH-001`:** Unify PNG (`renderer.py`) and SVG (`svg_renderer.py`) label placement (especially multi-point arrow labels), `textAlign`/`verticalAlign` handling, code block metrics, and `angle` rotation (`BUG-015`).
10. **`BUG-018`, `BUG-019`, `BUG-020`:** Fix `resolve_scene_layout()` magic frame coordinates, `_resolve_node_overlaps()` stale `y1_max`, and `move()` double-translation / cross-frame arrow detachment.
11. **`ARCH-002` & `ARCH-003`:** Extract shared atomic file-export helper using `dir_fd`/`O_NOFOLLOW`/`os.link` for PNG/SVG/Obsidian; fix `importer.py` merge-mode tombstone ID & `files` collisions; replace O(N) `_label_for` loops with `container_to_label` index.

### P3: Optimizations & Additional Capabilities
12. **`ARCH-004` & Cleanup:** Remove duplicate `export_to_excalidraw_url` & `read_diagram_guide` tools (fix `excalidraw://guide/{topic}`), align `skills.py`/`design_guide.py` with active toolsets, fix `capabilities_resource` stale comment, and optimize `SceneState` deepcopy/JSON serialization overhead for large scenes.
13. **Testing:** Add the regression, parity, cross-renderer, property-based, and 1,000+ element stress tests listed in Section 9.

---

## 14. Dependencies Between Fixes

```text
P0: Shared SceneService mutation helpers (BUG-003)
 ├──> P0: Atomic update_element (BUG-004)
 └──> P1: batch_mutate("connect") & draw_graph() eager routing (BUG-008)

P1: elements.text() uses measure_text_dimensions() (BUG-010)
 └──> P1: Pixel-accurate wrap_text_to_shape() (BUG-011)
       └──> P1: Diamond/Ellipse required_container_size() (BUG-012)
             └──> P0: auto_fix.py bound_t fix (BUG-001) produces accurate repairs

P1: routing.py adaptive stubs + source/target obstacles + port clamping (BUG-005, BUG-007)
 ├──> P1: Move/resize rerouting for elbowed arrows (BUG-009)
 ├──> P1: draw_graph() / batch_mutate("connect") eager routing (BUG-008)
 └──> P2: PNG/SVG multi-point arrow label parity (ARCH-001)
```

---

## 15. Acceptance Criteria for Major Fixes

- **`BUG-001` (`auto_fix.py`):** Given two shapes with bound labels of different lengths in any order, `diagnose_layout_issues()` reports the exact clipped shape and its own `bound_t["id"]`, and `apply_layout_repairs()` resizes only the clipped shape and updates its own `bound_t` text/bounds/position.
- **`BUG-002` (`auto_fix.py`):** `auto_fix_layout(repair_scope="overlaps")` or `"spacing"` never returns `"status": "repaired"` while `node_overlap` or `inconsistent_spacing` issues remain.
- **`BUG-003` & `BUG-004` (`batch_mutate`, `update_element`, `draw_architecture`):** `batch_mutate` exposes a typed `BatchOperation` schema; all batch actions match standalone `SceneService` outputs; `update_element` and `draw_architecture` increment `revision` by at most 1 and roll back completely on error.
- **`BUG-005`..`BUG-009` (Arrows):** `route_orthogonal_connector()` produces zero obstacle intersections (including `source`/`target` interiors) even with `20px` gaps; `draw_graph()` and `batch_mutate("connect")` store routed polylines for `elbowed=True`; moving/resizing a shape bound to an `elbowed=True` arrow succeeds and updates the route.
- **`BUG-010`..`BUG-012` (Text):** `elements.text()` width matches `measure_text_dimensions()`; `wrap_text_to_shape()` fits within `safe_w` for narrow shapes and wide Unicode/CJK strings; diamond and ellipse containers satisfy `w/W + h/H <= 1.0` and `(w/W)^2 + (h/H)^2 <= 1.0` respectively.
- **`ARCH-001` (Exports):** For any scene with routed multi-point connectors and aligned text, `render_scene_image()` (PNG) and `render_scene_svg()` (SVG) place connector labels at the same world coordinates and honor `textAlign`/`verticalAlign` consistently.
