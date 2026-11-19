# Migration Guide: Upgrading to exca-mcp v0.3.0

Version 0.3.0 introduces a major rationalization of the Excalidraw MCP tool surface. It reduces schema token consumption by over 50%, streamlines agent workflows, and promotes atomic batch authoring to the default profile, while retaining 100% of the underlying geometry, layout, routing, export, and interactive capabilities.

---

## Key Highlights

1. **Token Footprint Halved**:
   - The default `core` profile drops from 27 legacy tools (~9,472 tokens compact) to **12 curated tools (5,048 tokens compact)** — a 46.7% reduction.
   - The `full` profile drops from 48 tools (~16,010 tokens compact) to **20 tools (7,937 tokens compact)** — a 50.4% reduction.
   - Wire duplication eliminated: tool responses return minified compact JSON in `TextContent` without redundant schema echoing.

2. **`batch_mutate` Promoted to Core**:
   - Multi-step diagram generation no longer requires turn-by-turn roundtrips or setting `EXCALIDRAW_TOOLSET=full`.
   - Atomic multi-operation creation, styling, routing, and repair can be performed in a single call.

3. **Consolidated Tool Family**:
   - Related actions are merged into parameterized tools (`create_shape`, `create_connector`, `update_element`, `inspect_scene`, `generate_diagram`, `scene_storage`, `manage_element_state`, `live_server`).

4. **MCP Resources for Static Data**:
   - Font discovery (`list_fonts`) is now available at `excalidraw://fonts`.
   - Diagram guidelines are available at `excalidraw://guide/{topic}`.

5. **Preview Enhancements**:
   - `preview` now accepts `max_dimension` (default 1568px, matching Claude's optimal vision envelope) and `format` (`"png"` or `"jpeg"`).

---

## Complete Tool Migration Matrix (48 Baseline Tools -> v0.3.0)

| Legacy Tool (v0.2.x) | v0.3.0 Equivalent | Profile | Notes |
|---|---|---|---|
| `add_rectangle` | `create_shape(type="rectangle", x, y, w, h, ...)` | **core** | Merged into `create_shape`. |
| `add_circle` | `create_shape(type="ellipse", x, y, w, h, ...)` | **core** | Accepts `"ellipse"` or `"circle"`. |
| `add_diamond` | `create_shape(type="diamond", x, y, w, h, ...)` | **core** | Merged into `create_shape`. |
| `add_arrow` | `create_connector(x=..., y=..., x2=..., y2=..., ...)` | **core** | Coordinate-based arrow connector. |
| `connect` | `create_connector(source_id=..., target_id=..., ...)` | **core** | Element-bound smart connector with obstacle routing. |
| `add_frame` | `add_frame(name, x, y, w, h, element_ids)` | **core** | Unchanged. |
| `add_text` | `add_text(x, y, content, ...)` | **core** | Unchanged. |
| `move` | `update_element(element_id=..., x=..., y=...)` | **core** | Position updates absorbed into `update_element`. |
| `resize` | `update_element(element_id=..., width=..., height=...)` | **core** | Dimension updates absorbed into `update_element`. |
| `update_element` | `update_element(element_id=..., ...)` | **core** | Supports label, dimensions, position, styles, frame. |
| `delete` | `delete(element_id=...)` | **core** | Unchanged. |
| `clear` | `clear()` | **core** | Unchanged. |
| `undo` | `undo()` | **core** | Unchanged. |
| `auto_fix_layout` | `auto_fix_layout(...)` | **core** | Slim summary by default; `detailed=True` for full report. |
| `preview` | `preview(scale, padding, background, max_dimension, format)` | **core** | Added `max_dimension=1568` and `format="png"\|"jpeg"`. |
| `batch_mutate` | `batch_mutate(operations=[...])` | **core** | **Promoted from full to core.** Primary atomic authoring API. |
| `describe_scene` | `inspect_scene(mode="describe", detailed=...)` | **core** | Default `detailed=False` returns slim summary. |
| `get_scene_summary` | `inspect_scene(mode="summary")` | **core** | Unified scene inspection. |
| `get_scene` | `inspect_scene(mode="elements", offset=..., limit=...)` | **core** | Paginated element inspection. |
| `get_element` | `inspect_scene(mode="element", element_id=...)` | **core** | Single element property lookup. |
| `find_elements` | `inspect_scene(mode="find", query=..., type=...)` | **core** | Element filtering and querying. |
| `get_viewport` | `inspect_scene(mode="viewport")` | **core** | Camera viewport inspection. |
| `get_live_server_status` | `inspect_scene(mode="live_server")` | **core** | Live server status lookup. |
| `get_resource` | `inspect_scene(mode="resource", uri=...)` | **core** | Resource inspection lookup. |
| `draw_mermaid` | `generate_diagram(generator="mermaid", mermaid_code=...)` | **full** | Unified diagram generation. |
| `draw_architecture` | `generate_diagram(generator="architecture", prompt=...)` | **full** | Rapid shorthand architecture generator. |
| `draw_graph` | `generate_diagram(generator="graph", nodes=..., edges=...)` | **full** | Structured Sugiyama layout generator. |
| `save` | `scene_storage(action="save", name=...)` | **full** | Consolidated file persistence. |
| `load` | `scene_storage(action="load", name=...)` | **full** | Consolidated file persistence. |
| `list_saved_scenes` | `scene_storage(action="list")` | **full** | Returns stored scene names. |
| `export_scene` | `scene_storage(action="export")` | **full** | Returns raw Excalidraw JSON. |
| `import_scene` | `scene_storage(action="import", data=..., mode=...)` | **full** | Imports scene JSON/payload. |
| `export_png` | `export_png(name, directory, scale, padding, ...)` | **full** | Headless disk rasterization. |
| `set_element_locked` | `manage_element_state(action="lock"\|"unlock", element_ids=...)` | **full** | Unified element state management. |
| `lock_elements` | `manage_element_state(action="lock", element_ids=...)` | **full** | Removed legacy wrapper. |
| `unlock_elements` | `manage_element_state(action="unlock", element_ids=...)` | **full** | Removed legacy wrapper. |
| `manage_groups` | `manage_element_state(action="group"\|"ungroup", ...)` | **full** | Consolidated grouping control. |
| `group_elements` | `manage_element_state(action="group", element_ids=...)` | **full** | Removed legacy wrapper. |
| `ungroup_elements` | `manage_element_state(action="ungroup", group_id=...)` | **full** | Removed legacy wrapper. |
| `duplicate_elements` | `manage_element_state(action="duplicate", element_ids=...)` | **full** | Clones elements with spatial offset. |
| `add_code_block` | `batch_mutate(operations=[{"action": "add_code_block", ...}])` | **core** | Executed directly via atomic batch operation. |
| `set_viewport` | `set_viewport(scroll_x, scroll_y, zoom, focus_element_ids)` | **full** | Supports direct coordinate and auto-focus framing. |
| `focus_elements` | `set_viewport(focus_element_ids=...)` | **full** | Removed legacy wrapper. |
| `start_live_server` | `live_server(action="start", host=..., port=...)` | **full** | Merged into `live_server`. |
| `stop_live_server` | `live_server(action="stop")` | **full** | Merged into `live_server`. |
| `export_to_excalidraw_url` | `export_to_excalidraw_url(name=...)` | **full** | Client-side encrypted sharing. |
| `list_fonts` | Read MCP resource `excalidraw://fonts` | **resources** | Converted to static MCP resource. |
| `read_diagram_guide` | `read_diagram_guide(topic=...)` / `excalidraw://guide/{topic}` | **full** / **resources** | Available as tool fallback and resource. |

---

## Code Examples: Before and After

### 1. Creating Connected Shapes

**Before (v0.2.x):**
```python
r1 = add_rectangle(x=100, y=100, w=120, h=60, label="Service A")
r2 = add_rectangle(x=300, y=100, w=120, h=60, label="Service B")
connect(source_id=r1["rectangle_id"], target_id=r2["rectangle_id"], label="HTTP")
```

**After (v0.3.0):**
```python
r1 = create_shape(type="rectangle", x=100, y=100, w=120, h=60, label="Service A")
r2 = create_shape(type="rectangle", x=300, y=100, w=120, h=60, label="Service B")
create_connector(source_id=r1["rectangle_id"], target_id=r2["rectangle_id"], label="HTTP")
```

### 2. Atomic Authoring via `batch_mutate` (Now in Core)

```python
batch_mutate(operations=[
    {"action": "create_shape", "type": "rectangle", "client_id": "api", "x": 100, "y": 100, "w": 140, "h": 70, "label": "API Gateway"},
    {"action": "create_shape", "type": "diamond", "client_id": "auth", "x": 320, "y": 100, "w": 100, "h": 100, "label": "Auth Check"},
    {"action": "create_connector", "source_id": "$api", "target_id": "$auth", "label": "Authorize", "elbowed": True},
    {"action": "auto_fix_layout", "repair_scope": "all"}
])
```

### 3. Querying Scene State

**Before (v0.2.x):**
```python
summary = get_scene_summary()
elements = get_scene(limit=20)
matches = find_elements(type="rectangle")
```

**After (v0.3.0):**
```python
summary = inspect_scene(mode="summary")
elements = inspect_scene(mode="elements", limit=20)
matches = inspect_scene(mode="find", type="rectangle")
```
