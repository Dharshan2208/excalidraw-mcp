# MCP tools and resources

All domain failures are MCP tool errors. Numeric inputs and style values have
JSON Schema bounds/enums, structured dictionary results have output schemas, and
tools advertise read-only, destructive, idempotent, and open-world hints where
applicable.

## Toolset Configuration (`EXCALIDRAW_TOOLSET`)

The server supports two toolset modes controlled by the `EXCALIDRAW_TOOLSET` environment variable:
- `core` (default): Streamlined 27-tool set covering standard generation, mutation, inspection, auto-repair, and export workflows with a 45.2% reduction in schema tokens.
- `full`: Complete 48-tool set including advanced graph generation (`draw_graph`), batch mutations (`batch_mutate`), live canvas background server (`start_live_server`), viewport camera controls, element locking, and grouping.

Zero-token capability discovery is available via the MCP resource `excalidraw://capabilities`.

## Create and edit

- `add_rectangle`, `add_circle`, `add_diamond`: add a shape and optional label;
  supports `roundness` ("adaptive", "round", "sharp") and `frame_id`; returns the shape ID and `label_id`.
- `add_arrow`: add a coordinate-based arrow (supports `elbowed=True/False`) and optional bound label.
- `add_text`: add standalone text with optional `frame_id`.
- `add_code_block`: add a syntax-highlighted code block with window controls, configurable themes, line numbers,
  and monospace typography.
- `add_frame`: create an Excalidraw frame container (`name`, `x`, `y`, `w`, `h`) and optionally parent
  initial elements inside it.
- `connect`: connect two existing shapes by ID (supports `elbowed=True/False`). The arrow starts and ends at
  approximate shape boundaries and follows later shape moves/resizes.
- `move`: move a container with its label and connector endpoints. Moving a frame automatically moves all
  contained children. Moving bound text independently is rejected. Moving an arrow directly detaches its endpoints.
- `resize`: resize rectangles, ellipses, diamonds, and frames, recenter labels, and reroute fully bound connectors.
- `update_element`: update an element's label, styling, `roundness`, `elbowed` connector mode, or `frame_id` parent.
  Passing an empty label removes a container label. Standalone text cannot be empty; delete it. Setting `frame_id=""`
  unparents an element.
- `delete`: delete an element and its owned label, cleaning reverse bindings. Deleting a frame unparents its children
  without deleting them.
- `batch_mutate`: execute multiple creation, movement, connection, styling, and resizing operations atomically in a single
  revision step. Supports dynamic `client_id` reference resolution across operations and rolls back 100% on any failure.
- `auto_fix_layout(name=None, dry_run=False, repair_scope="all", aggressiveness="balanced", min_gap=30.0)`:
  diagnose, plan, and automatically repair layout defects (overlaps, text clipping, containment violations, connector collisions, and crowded spacing) with transactional rollback safety.
  Executes repairs in 5 topological phases:
  1. Container resizing for text containment (expanding outward from center).
  2. Minimal-displacement de-collision with group alignment preservation.
  3. Frame boundary expansion with configurable padding.
  4. Obstacle-aware orthogonal connector rerouting with clearance corridors.
  5. Spacing adjustments for crowded components.
  Supports `dry_run=True` for non-mutating preview and automatically rolls back if regressions are detected. Returns `AutoFixLayoutResult`.
- `clear`: reset elements, app state, and embedded files.
- `undo`: restore the snapshot before the latest successful mutation. History is
  bounded by `EXCALIDRAW_HISTORY_LIMIT` and `EXCALIDRAW_MAX_HISTORY_BYTES`;
  failed operations and reads add no entry or consume existing history.

## Inspect and persist

- `find_elements(query=None, type=None, frame_id=None, element_id=None, connected_to=None, include_bound_labels=False, limit=50)`:
  flexible query tool filtering active elements by text search, element type, frame membership, ID, or graph connectivity.
- `list_fonts(category=None)`: discover and inspect all TrueType/OpenType fonts available in the execution environment.
- `get_scene(offset=0, limit=50)`: returns up to 200 active elements per page,
  total count, current revision, and `has_more`.
- `get_element(element_id)`: returns one active element and scene revision.
- `list_saved_scenes`: returns validated regular-file names in configured storage.
- `save(name, overwrite=false)`: atomically writes a complete server-local file.
- `load(name)`: validates and replaces the active scene. A concurrent edit makes
  the operation fail instead of being overwritten. Persisted byte and document
  element limits are enforced before the active scene changes.
- `set_element_locked(element_ids, locked=True)`: unified tool to lock or unlock elements and their bound labels (also supports legacy `lock_elements` and `unlock_elements` wrappers).
- `manage_groups(element_ids=None, group_id=None, action="group")`: unified tool to group or ungroup diagram components (also supports legacy `group_elements` and `ungroup_elements` wrappers).
- `set_viewport(scroll_x=None, scroll_y=None, zoom=None, background_color=None, focus_element_ids=None, padding=50)`: configure camera scroll, zoom, and background color, or auto-frame camera on specific elements.
- `preview(scale=1.0, padding=40, background=true)`: renders an inline PNG image preview of the active Excalidraw scene
  directly into the MCP client conversation without writing a local file.
- `export_png(name, directory=None, scale=1.0, padding=40, background=true, overwrite=false)`: exports the active diagram
  directly to a PNG image file in a project folder or configured export directory.
- `export_scene`: embeds a complete `.excalidraw` snapshot in the result without
  writing to disk, subject to `EXCALIDRAW_MAX_EXPORT_BYTES`.
- `draw_architecture`: compatibility shorthand for comma/newline components such
  as `box: API, circle: Database`. It is a list DSL, not natural-language parsing.
- `draw_graph`: structured graph generation supporting layered/horizontal/vertical layouts, subgraph clusters (frames),
  elbowed edge routing, and adaptive corner roundness. Described in `graph-generation.md`.

Saved documents are also readable without changing the active scene through the
resource template `excalidraw://scenes/{name}.excalidraw`. The same name rules and
storage confinement as `load` apply.

Tools that remove or replace content (`delete`, `clear`, `load`,
`draw_architecture`, and `draw_graph`) are marked destructive. File operations
are marked open-world because they access configured server storage. Scene
inspection and export are read-only. `save(overwrite=true)` can replace a file
and is marked destructive.

The server is process-local. Creating multiple server instances through
`create_server()` gives each its own scene, but enabling a shared HTTP transport
would still require authentication and per-user lifecycle design.
