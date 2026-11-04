# MCP Tools Reference

> **:** > **BREAKING CHANGE (v0.2.0)**: The default server configuration now exposes the streamlined **`CORE` toolset (27 tools)** instead of the full 48-tool set, reducing prompt schema overhead by 45.2% (~6,560 tokens per turn). If your agent workflows or MCP clients require advanced tools (`draw_graph`, `batch_mutate`, camera viewports, element locking, grouping, or the background live canvas server), restore the previous 48-tool behavior by setting the environment variable:
> ```bash
> export EXCALIDRAW_TOOLSET=full
> ```

The server supports two configurable toolsets controlled by `EXCALIDRAW_TOOLSET`:
- **`CORE` Set (27 tools, Default)**: The essential generation-edit-inspect-validate-export workflow for autonomous coding agents. Saves **45.2% in schema tokens** (~6,560 tokens per turn).
- **`FULL` Set (48 tools)**: Includes all `CORE` tools plus advanced layered graph generators (`draw_graph`), atomic batch transactions (`batch_mutate`), element locking, grouping, camera viewports, and the background live canvas server.

All tools are strictly typed with JSON Schema bounds and explicit safety hints (`readOnly`, `destructive`, `idempotent`).

### 1. High Level Generation & Design Guidance

| Tool | Toolset | Inputs | Outputs | Description |
|---|---|---|---|---|
| `draw_mermaid` | **CORE** | `mermaid_code: str`<br>`direction: str | None = None`<br>`layout: str = "layered"`<br>`elbowed: bool = False`<br>`roundness: str | None = None` | `GraphResult`<br>`{ status, nodes, edges, node_map, edge_map, cluster_map, revision }` | Parses Mermaid flowchart/graph syntax (`graph TD`, `flowchart LR`, subgraphs, node shapes, edge styles) and renders directly to Excalidraw with automatic text containment. |
| `draw_architecture` | **CORE** | `prompt: str` (e.g., `"box: Frontend, db: Postgres"`)<br>`wrap_threshold: int = 4`<br>Optional styles (`strokeColor`, `backgroundColor`, etc.) | `ArchitectureResult`<br>`{ revision, element_count, components }` | Rapid diagram generator parsing comma/newline-separated shorthand syntax (`box`, `circle`, `diamond`) with grid-wrapping and automatic obstacle-avoiding connectors. |
| `draw_graph` | FULL | `nodes: list[GraphNode]`<br>`edges: list[GraphEdge]`<br>`clusters: list[GraphCluster] = None`<br>`layout: str = "layered"` (`layered`, `horizontal`, `vertical`)<br>`direction: str = "horizontal"` (`horizontal`, `vertical`)<br>`elbowed: bool = False`<br>`roundness: str | None = None` | `GraphResult`<br>`{ revision, element_count, node_map, edge_map, cluster_map }` | Replaces the scene with a structured diagram using automatic topological ranking, obstacle aware edge routing, clustered frame grouping, and font aware label wrapping. Returns stable logical to element ID mappings. |
| `read_diagram_guide` | FULL | `topic: str | None = None` (`layout`, `colors`, `typography`, `grouping`, `arrows`, `spacing` ) | `DiagramGuideResult`<br>`{ topic, guide, available_topics }` | Practical diagram design guidelines covering 60-30-10 color rules, semantic palettes, standard node dimensions, margins, orthogonal arrow routing, and readability. |

### 2. Primitive Shapes, Text, Code Blocks & Frames

| Tool | Toolset | Inputs | Outputs | Description |
|---|---|---|---|---|
| `add_rectangle` | **CORE** | `x: float`, `y: float`, `w: float`, `h: float`<br>`label: str = ""` + styles + `roundness: str = None`, `frame_id: str = None` | `CreateResult`<br>`{ rectangle_id, label_id }` | Adds a rectangle to the active scene with an optional centered bound label, adaptive/round corner roundness, frame membership, and automatic outward expansion. |
| `add_circle` | **CORE** | `x: float`, `y: float`, `size: float`<br>`label: str = ""` + styles + `frame_id: str = None` | `CreateResult`<br>`{ circle_id, label_id }` | Adds a circle (ellipse) with an optional centered bound label, ellipse inscribed boundary containment, and frame membership. |
| `add_diamond` | **CORE** | `x: float`, `y: float`, `w: float`, `h: float`<br>`label: str = ""` + styles + `roundness: str = None`, `frame_id: str = None` | `CreateResult`<br>`{ diamond_id, label_id }` | Adds a decision diamond with rhombus inscribed boundary containment, adaptive roundness, and frame membership. |
| `add_arrow` | **CORE** | `x: float`, `y: float`, `x2: float`, `y2: float`<br>`label: str = ""` + styles + `elbowed: bool = False` | `CreateResult`<br>`{ arrow_id, label_id }` | Adds a directional arrow (straight or elbowed) with an optional corridor positioned label. |
| `add_text` | **CORE** | `x: float`, `y: float`, `content: str`<br>`font_size: int = 20` + styles + `frame_id: str = None` | `CreateResult`<br>`{ text_id }` | Creates a standalone text element with accurate FreeType font metrics and optional frame membership. |
| `connect` | **CORE** | `source_id: str`, `target_id: str`<br>`label: str = ""` + styles + `elbowed: bool = False` | `ConnectResult`<br>`{ arrow_id, label_id }` | Binds two existing shapes with obstacle aware orthogonal routing, cardinal face boundary docking, and multi edge lane separation. |
| `add_frame` | **CORE** | `name: str = ""`, `x: float`, `y: float`, `w: float`, `h: float`<br>`element_ids: list[str] = None` | `CreateResult`<br>`{ frame_id }` | Creates an Excalidraw frame container and optionally parents specified elements inside it. |
| `add_code_block` | FULL | `code: str`<br>`language: str = "python"`<br>`x: float = 0`, `y: float = 0`<br>`title: str = None`<br>`theme: str = "dark"`<br>`font_size: int = 14`<br>`line_numbers: bool = True`<br>`w: float = None`, `h: float = None`<br>`frame_id: str = None` | `CodeBlockResult`<br>`{ status, container_id, text_id, width, height, revision }` | Adds a syntax highlighted code block with window controls, configurable themes, line numbers, and monospace typography. |

### 3. Scene Editing & Manipulation

| Tool | Toolset | Inputs | Outputs | Description |
|---|---|---|---|---|
| `move` | **CORE** | `element_id: str`, `x: float`, `y: float` | `MoveResult`<br>`{ status, element_id, x, y }` | Repositions an element. Moving a frame moves all contained elements; moving grouped elements moves group members together; rejects locked elements. |
| `resize` | **CORE** | `element_id: str`, `width: float`, `height: float` | `ResizeResult`<br>`{ status, element_id, width, height }` | Resizes a shape or frame, recalculates label centering, and reroutes connected arrows; rejects locked elements. |
| `update_element` | **CORE** | `element_id: str`<br>`label: str | None = None` + styles + `roundness`, `elbowed`, `frame_id` | `UpdateResult`<br>`{ status, element_id, label_id }` | Modifies an element's label, styling, roundness mode, elbowed connector routing, or frame assignment with automatic center anchored container expansion. |
| `delete` | **CORE** | `element_id: str` | `DeleteResult`<br>`{ status, deleted_ids }` | Deletes an element and its bound label; unparents frame children if a frame is deleted; cleans up references in connected arrows; rejects locked elements. |
| `auto_fix_layout` | **CORE** | `name: str \| None = None`<br>`dry_run: bool = False`<br>`repair_scope: str = "all"`<br>`aggressiveness: str = "balanced"`<br>`min_gap: float = 30.0` | `AutoFixLayoutResult`<br>`{ status, dry_run, initial_issues, final_issues, fixed_issues_count, unresolved_issues, planned_changes, applied_changes, changed_element_ids, skipped_repairs, warnings, rolled_back, revision }` | Diagnoses, plans, and repairs layout defects (overlaps, text clipping, containment violations, connector collisions, and crowded spacing) with transactional rollback safety across 5 strict topological phases. |
| `clear` | **CORE** | None | `DeleteResult`<br>`{ status }` | Wipes the entire scene, active elements, and embedded state. |
| `undo` | **CORE** | None | `UndoResult`<br>`{ status, revision }` | Rolls back the scene to the state immediately preceding the latest mutation. |
| `set_element_locked` | FULL | `element_ids: list[str]`, `locked: bool = True` | `LockResult \| UnlockResult`<br>`{ status, element_ids, revision }` | Unified tool to lock or unlock elements and their bound labels to prevent or permit mutations. |
| `lock_elements` | FULL | `element_ids: list[str]` | `LockResult`<br>`{ status, element_ids, revision }` | Legacy wrapper calling `set_element_locked(element_ids, locked=True)`. |
| `unlock_elements` | FULL | `element_ids: list[str]` | `UnlockResult`<br>`{ status, element_ids, revision }` | Legacy wrapper calling `set_element_locked(element_ids, locked=False)`. |
| `manage_groups` | FULL | `element_ids: list[str] = None`<br>`group_id: str = None`<br>`action: str = "group"` (`group`, `ungroup`) | `GroupResult \| UngroupResult` | Unified tool to group elements together or disband existing groups. |
| `group_elements` | FULL | `element_ids: list[str]` | `GroupResult`<br>`{ status, group_id, element_ids, revision }` | Legacy wrapper calling `manage_groups(element_ids=element_ids, action="group")`. |
| `ungroup_elements` | FULL | `element_ids: list[str] = None`<br>`group_id: str = None` | `UngroupResult`<br>`{ status, affected_elements, removed_group_ids, revision }` | Legacy wrapper calling `manage_groups(element_ids=element_ids, group_id=group_id, action="ungroup")`. |
| `duplicate_elements` | FULL | `element_ids: list[str]`<br>`offset_x: float = 20.0`<br>`offset_y: float = 20.0` | `DuplicateResult`<br>`{ status, original_ids, duplicated_ids, id_mapping, revision }` | Duplicates multiple elements with spatial offsets, relationship remapping, arrow endpoint retargeting, bound label cloning, and group isolation. |
| `batch_mutate` | FULL | `operations: list[dict]` | `BatchResult`<br>`{ status, operations_executed, ref_map, results, revision }` | Atomically executes multiple creation, connection, movement, resize, lock, group, duplicate, auto_fix_layout, or update actions in a single revision step with dynamic `client_id` resolution. |

### 4. Inspection, Viewport, Query, Export & Sharing

| Tool | Toolset | Inputs | Outputs | Description |
|---|---|---|---|---|
| `describe_scene` | **CORE** | `detailed: bool = True` | `SceneDescriptionResult`<br>`{ summary, element_count, layout_type, elements, connections, bounds, revision }` | Produces an AI-readable summary of elements, positions, labels, flow connections, topological layout, and bounds. |
| `get_scene_summary` | **CORE** | None | `SceneSummaryResult`<br>`{ element_count, type_counts, frames, groups, connectors, code_blocks, standalone_elements, bounds, description, revision }` | Provides a structured semantic overview and topological understanding of the entire diagram for AI agent reasoning. |
| `get_scene` | **CORE** | `offset: int = 0`, `limit: int = 50` | `ScenePage`<br>`{ elements, total, offset, limit, has_more, revision }` | Paginated inspection of all elements currently on the canvas. |
| `get_element` | **CORE** | `element_id: str` | `ElementResult`<br>`{ element, revision }` | Fetches details and properties of a single element by its ID. |
| `preview` | **CORE** | `scale: float = 1.0`<br>`padding: int = 40`<br>`background: bool = True` | `ImageContent`<br>(`image/png`) | Renders an inline PNG image preview of the active Excalidraw canvas directly into the chat conversation with dynamic canvas scaling up to 8K. |
| `export_png` | **CORE** | `name: str`<br>`directory: str | None = None`<br>`scale: float = 1.0`<br>`padding: int = 40`<br>`background: bool = True`<br>`overwrite: bool = False` | `PngExportResult`<br>`{ status, name, path, bytes, width, height }` | Atomically exports the active scene directly to a PNG image file in a project folder or configured directory. |
| `save` | **CORE** | `name: str`, `overwrite: bool = False` | `SaveResult`<br>`{ status, name, path }` | Atomically writes the scene to server disk in `.excalidraw` JSON format. |
| `load` | **CORE** | `name: str` | `LoadResult`<br>`{ status, name, elements }` | Atomically loads a saved `.excalidraw` file and sets it as the active scene. |
| `export_scene` | **CORE** | None | `EmbeddedResource`<br>(`application/vnd.excalidraw+json`) | Emits the entire `.excalidraw` schema v2 document directly into the MCP message. |
| `set_viewport` | FULL | `scroll_x: float = None`<br>`scroll_y: float = None`<br>`zoom: float = None`<br>`background_color: str = None`<br>`focus_element_ids: list[str] = None`<br>`padding: int = 50` | `ViewportResult \| FocusResult` | Updates canvas camera scroll offsets, zoom level, background canvas color, or automatically frames on specified elements. |
| `get_viewport` | FULL | None | `ViewportResult`<br>`{ scroll_x, scroll_y, zoom, view_background_color, revision }` | Inspects current canvas camera scroll coordinates, zoom factor, and background color. |
| `focus_elements` | FULL | `element_ids: list[str] = None`<br>`padding: int = 50` | `FocusResult`<br>`{ status, scroll_x, scroll_y, zoom, bounding_box, focused_element_ids, revision }` | Legacy wrapper delegating to `set_viewport(focus_element_ids=element_ids, padding=padding)`. |
| `find_elements` | **CORE** | `query: str | None`<br>`type: str | None`<br>`frame_id: str | None`<br>`element_id: str | None`<br>`connected_to: str | None`<br>`include_bound_labels: bool = False`<br>`limit: int = 50` | `FindResult`<br>`{ matches, total, revision }` | Filters active elements by text search, element type, parent frame, ID, or graph connectivity. |
| `list_saved_scenes`| FULL | None | `SavedScenesResult`<br>`{ scenes: list[str] }` | Returns a list of all scene files stored in the persistent directory. |
| `list_fonts` | FULL | `category: str | None` (`sans-serif`, `monospace`, `serif`, `handwriting`) | `FontListResult`<br>`{ fonts, total, defaults }` | Discovers and lists available system fonts and semantic font categories. |
| `get_resource` | **CORE** | `uri: str | None = None`<br>`resource_type: str | None = None`<br>`identifier: str | None = None` | `ResourceResult`<br>`{ resource_type, identifier, document, theme, library, element, ... }` | Retrieves scene, library (`architecture`, `flowchart`, `cloud`), theme (`default`, `dark`, `light`, `monokai`, `nord`, `solarized`), or element resources through a unified interface. |
| `import_scene` | FULL | `data: str`<br>`mode: str = "replace"` (`replace`, `merge`)<br>`offset_x: float = 0.0`<br>`offset_y: float = 0.0` | `ImportResult`<br>`{ status, mode, elements_imported, total_elements, id_mapping, revision }` | Imports Excalidraw scenes from raw JSON, `.excalidraw` files, Obsidian `.excalidraw.md` files, or embedded PNGs with reference preservation and collision remapping. |
| `export_to_excalidraw_url` | FULL | `name: str | None = None` | `ShareUrlResult`<br>`{ status, url, id, revision }` | Publishes active or saved scene to excalidraw.com using 128-bit AES-GCM client-side encryption and returns a shareable URL. |

### 5. Live Canvas Server & Browser Synchronization

| Tool | Toolset | Inputs | Outputs | Description |
|---|---|---|---|---|
| `start_live_server` | FULL | `host: str = "127.0.0.1"`<br>`port: int = 8080` | `LiveServerResult`<br>`{ status, url, host, port }` | Launches the interactive browser connected live canvas server with real-time WebSocket synchronization. |
| `stop_live_server` | FULL | None | `LiveServerResult`<br>`{ status }` | Gracefully shuts down the background live canvas server and closes active client connections. |
| `get_live_server_status` | FULL | None | `LiveServerResult`<br>`{ is_running, url, host, port, active_clients }` | Reports operational status, connection URL, and connected client count of the live canvas server. |

#### Live Server Authentication & Security

- **Token Authentication (`EXCALIDRAW_LIVE_TOKEN`)**:
  Protect live canvas synchronization by setting the `EXCALIDRAW_LIVE_TOKEN` environment variable to a shared secret. When configured:
  - **Browser UI (`GET /`)**: The web UI automatically injects the secret into its WebSocket connection (`/ws?token=<token>`), allowing authenticated browser tabs to load and edit seamlessly.
  - **REST API (`POST /api/scene`)**: Mutating requests require the token via:
    - HTTP header `Authorization: Bearer <token>`
    - HTTP header `x-auth-token: <token>`
    - Query parameter `?token=<token>`
    - Unauthenticated mutations are rejected with HTTP `401 Unauthorized`.
  - **WebSocket Sync (`/ws`)**: WebSockets require the token via `?token=<token>` query parameter or `x-auth-token` header. Unauthorized connections are rejected immediately with close code `1008` (Policy Violation).
  - **Read-Only Endpoints**: Diagnostic and preview endpoints (`GET /api/scene`, `GET /api/health`, `GET /api/screenshot`) remain accessible for health monitors and visual previews.

- **Cross-Site WebSocket Hijacking (CSWSH) Protection**:
  The live canvas WebSocket handler enforces strict origin validation. Connections with non-local `Origin` headers (outside `localhost`, `127.0.0.1`, `::1`, and the configured server host) are rejected with close code `1008`.

- **Remote Network Binding (`EXCALIDRAW_ALLOW_REMOTE`)**:
  By default, binding `start_live_server` to `0.0.0.0` or `::` (all network interfaces) is blocked with a `SceneError` to prevent inadvertent public exposure. To allow binding to all interfaces (required inside Docker containers or when hosting across a local area network), set:
  ```bash
  export EXCALIDRAW_ALLOW_REMOTE=1
  ```
  > **:** > When setting `EXCALIDRAW_ALLOW_REMOTE=1`, always configure `EXCALIDRAW_LIVE_TOKEN` to prevent unauthorized network users from modifying your canvas.

---
