# MCP Tools Reference

> **BREAKING CHANGE (v0.3.0)**: Tool surface has been rationalized from 48 legacy tools to **12 tools in the default `core` profile** and **20 tools in the `full` profile**, reducing schema token overhead by over 50%.
> - **`CORE` Toolset (12 tools, Default)**: The essential generation, editing, inspection, validation, batch mutation, and preview surface for autonomous AI coding agents.
> - **`FULL` Toolset (20 tools)**: Adds persistent diagram file storage (`scene_storage`), high-resolution disk export (`export_png`), advanced generators (`generate_diagram`), element locking and grouping (`manage_element_state`), camera viewport framing (`set_viewport`), background live WebSocket server (`live_server`), client-side encrypted sharing (`export_to_excalidraw_url`), and design guidelines (`read_diagram_guide`).
>
> To enable the `FULL` toolset, configure the environment variable:
> ```bash
> export EXCALIDRAW_TOOLSET=full
> ```
> For migrating existing workflows from v0.2.x, see [docs/migration_v030.md](migration_v030.md).

All tools feature strictly typed Pydantic parameters, stripped `outputSchema` overhead, minified compact JSON response serialization, and explicit MCP safety annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`).

---

## 1. Core Profile Tools (12 Tools — Default)

The default `core` toolset contains all capabilities required to construct, connect, inspect, repair, and preview Excalidraw diagrams.

| Tool | Profile | Safety Annotations | Inputs Summary | Description |
|---|---|---|---|---|
| `create_shape` | **CORE** | Mutating | `type: "rectangle" \| "ellipse" \| "diamond" \| "circle"`<br>`x: float, y: float, w: float, h: float`<br>`label: str = ""` + styles + `frame_id: str = None` | Creates a rectangle, ellipse/circle, or decision diamond with automatic font-aware text containment, centering, and frame parentage. |
| `create_connector` | **CORE** | Mutating | `x: float = None, y: float = None, x2: float = None, y2: float = None`<br>`source_id: str = None, target_id: str = None`<br>`label: str = ""` + styles + `elbowed: bool = False` | Creates a directional arrow. Connects arbitrary canvas coordinates or binds two existing shapes with obstacle-avoiding orthogonal routing, cardinal docking ports, and multi-lane separation. |
| `add_text` | **CORE** | Mutating | `x: float, y: float, content: str`<br>`font_size: int = 20` + styles + `frame_id: str = None` | Creates a standalone text element with FreeType font metrics and optional frame membership. |
| `add_frame` | **CORE** | Mutating | `name: str = ""`, `x: float, y: float, w: float, h: float`<br>`element_ids: list[str] = None` | Creates a container frame and optionally parents specified elements inside it. |
| `update_element` | **CORE** | Mutating | `element_id: str`<br>`x: float = None, y: float = None`<br>`width: float = None, height: float = None`<br>`label: str = None` + styles + `frame_id: str = None` | Unified element mutation: updates spatial coordinates, dimensions, bound text label, visual styling, corner roundness, or frame assignment. |
| `delete` | **CORE** | Destructive | `element_id: str` | Deletes an element and its bound label; cleans up connector bindings; rejects locked elements. |
| `clear` | **CORE** | Destructive | None | Atomically wipes the entire active canvas and element state. |
| `batch_mutate` | **CORE** | Mutating | `operations: list[dict]` | Atomically executes multiple shape, connector, movement, style, lock, group, duplicate, or code block operations in a single revision step with dynamic `$ref` client ID resolution. |
| `inspect_scene` | **CORE** | Read-Only | `mode: "summary" \| "describe" \| "elements" \| "element" \| "find" \| "viewport" \| "live_server" \| "resource"`<br>Mode-specific parameters (`element_id`, `query`, `detailed`, `limit`, `offset`, etc.) | Unified query interface for scene summaries, AI-readable topological descriptions, element properties, paginated listings, and search filters. |
| `auto_fix_layout` | **CORE** | Mutating, Idempotent | `dry_run: bool = False`<br>`repair_scope: "all" \| "overlaps" \| "connectors" \| "containment" \| "text" \| "spacing" = "all"`<br>`aggressiveness: "gentle" \| "balanced" \| "aggressive" = "balanced"`<br>`min_gap: float = 30.0`<br>`verbose: bool = False`<br>`name: str = None` | Five-phase topological layout diagnostic and repair engine with automatic regression rollback. Slim summary returned by default. |
| `undo` | **CORE** | Mutating | None | Reverts the canvas to the state immediately preceding the latest mutation using the in-memory undo stack. |
| `preview` | **CORE** | Read-Only | `scale: float = 1.0`<br>`padding: int = 40`<br>`background: bool = True`<br>`max_dimension: int = 1568`<br>`format: "png" \| "jpeg" = "png"` | Renders an inline image preview directly into LLM turns. Caps maximum dimension maintaining aspect ratio (default 1568px) and supports PNG or JPEG output. |

---

## 2. Full Profile Tools (8 Additional Tools — 20 Total)

The `full` profile includes all 12 core tools plus 8 advanced management, generation, and persistence tools.

| Tool | Profile | Safety Annotations | Inputs Summary | Description |
|---|---|---|---|---|
| `scene_storage` | FULL | Destructive | `action: "save" \| "load" \| "list" \| "export" \| "import" \| "share_url"`<br>`name: str = None, overwrite: bool = False`<br>`data: str = None, mode: "replace" \| "merge" = "replace"` | Consolidated scene persistence: atomically saves, loads, lists, exports, or imports native `.excalidraw` JSON documents, or generates an encrypted shareable link. |
| `export_png` | FULL | Read-Only, Idempotent | `name: str`<br>`directory: str = None`<br>`scale: float = 1.0, padding: int = 40`<br>`background: bool = True, overwrite: bool = False` | Headless rasterization exporting the active scene to a high-resolution PNG file on server disk. |
| `generate_diagram` | FULL | Destructive | `format: "mermaid" \| "architecture" \| "graph"`<br>`mermaid_code: str = None`<br>`prompt: str = None`<br>`nodes: list[GraphNode] = None, edges: list[GraphEdge] = None`<br>Layout controls (`direction`, `elbowed`, `roundness`, etc.) | Unified generator: builds diagrams from Mermaid syntax, rapid shorthand architecture strings, or structured Sugiyama node/edge graphs with automatic frame clustering. |
| `manage_element_state` | FULL | Mutating, Idempotent | `action: "lock" \| "unlock" \| "group" \| "ungroup" \| "duplicate"`<br>`element_ids: list[str] = None`<br>`group_id: str = None`<br>`offset_x: float = 20.0, offset_y: float = 20.0` | Unified management of element lock protection, logical grouping/ungrouping, and spatial duplication with relationship remapping. |
| `set_viewport` | FULL | Mutating, Idempotent | `scroll_x: float = None, scroll_y: float = None`<br>`zoom: float = None, background_color: str = None`<br>`focus_element_ids: list[str] = None, padding: int = 50` | Sets camera scroll coordinates, zoom level, background canvas color, or automatically calculates bounding box framing on specified elements. |
| `live_server` | FULL | Idempotent, Open-World | `action: "start" \| "stop"`<br>`host: str = "127.0.0.1", port: int = 8080` | Starts or stops the background WebSocket-enabled live canvas visualizer for real-time browser synchronization. |
| `export_to_excalidraw_url` | FULL | Read-Only, Open-World | `name: str = None` | Publishes the scene to excalidraw.com using 128-bit client-side AES-GCM encryption and returns a shareable link. |
| `read_diagram_guide` | FULL | Read-Only | `topic: str = None` (`layout`, `colors`, `typography`, `grouping`, `arrows`, `spacing`, `readability`) | Returns practical diagram design guidelines covering 60-30-10 color rules, spacing, and readability. Prefer reading resource `excalidraw://guide/{topic}`. |

---

## 3. MCP Resources

Resources allow clients and models to discover metadata, documentation, and saved scenes without consuming turn-by-turn tool execution tokens.

| Resource URI | MIME Type | Description |
|---|---|---|
| `excalidraw://fonts` | `application/json` | Discovers available system fonts, Excalifont paths, and semantic font family categories (`sans-serif`, `monospace`, `handwriting`). |
| `excalidraw://guide/{topic}` | `text/markdown` | Parameterized design guide returning markdown principles and recommendations for `layout`, `colors`, `typography`, `grouping`, `arrows`, and `spacing`. |
| `excalidraw://capabilities` | `application/json` | Active server metadata, toolset configuration (`core` vs `full`), tool counts, and storage paths. |
| `excalidraw://scenes/{name}.excalidraw` | `application/vnd.excalidraw+json` | Reads a saved scene directly from storage without changing the active working canvas. |
| `exca-mcp://skills/index` | `application/json` | Index of all bundled AI agent skills and reference guides. |
| `exca-mcp://skills/{name}` | `text/markdown` | Full content of a specific packaged agent skill. |

---

## 4. MCP Task Prompts

Clients can invoke pre-configured task prompts that guide AI models through multi-step diagramming tasks:

| Prompt Name | Arguments | Description |
|---|---|---|
| `create_architecture_diagram` | `system_description`, `style="modern"`, `output_name="architecture"` | Strict 10-step process guiding the agent to plan tiers, construct via primitives, diagnose geometry, auto-repair, and export. |
| `create_flowchart` | `process_description`, `direction="TB"`, `output_name="flowchart"` | Guides construction of flowcharts with single starts, clear terminals, labeled decision diamonds, and perimeter loops. |
| `plan_diagram` | `request`, `diagram_type="architecture"` | Guides the upfront planning phase (node density caps, 60-30-10 palette selection, tier structure) before drawing. |
| `edit_existing_diagram` | `instructions`, `scene_name=""` | Guides non-destructive updates to active or saved diagrams while preserving existing layout and hierarchy. |
| `verify_and_export_diagram` | `output_name="diagram"`, `directory="docs"` | 5-step quality gate: auto-repair diagnostics, visual review, human editability check, and dual `.excalidraw` + PNG export. |

---

## 5. Parameter Reference & Practical Examples

### `create_shape`
Creates a geometric primitive (`"rectangle"`, `"ellipse"`, `"diamond"`, or `"circle"`) with font-aware label containment:

```python
shape = create_shape(
    type="rectangle",             # "rectangle" | "ellipse" | "diamond" | "circle"
    x=100.0,
    y=120.0,
    w=200.0,
    h=90.0,                       # Defaults to w if None
    label="Order Service\nREST",
    frame_id=None,                # Optional parent frame ID
    roundness="adaptive",         # "adaptive" | "round" | "sharp"
    backgroundColor="#e7f5ff",    # Hex color code
    strokeColor="#1971c2",
    fillStyle="solid",            # "solid" | "hachure" | "cross-hatch" | "zigzag"
    strokeWidth=2,                # 1 to 20
    strokeStyle="solid",          # "solid" | "dashed" | "dotted"
    opacity=100,                  # 0 to 100
    roughness=1,                  # 0 to 3
    font_family="sans-serif",     # "sans-serif" | "excalifont" | "monospace" | "comic-shanns"
    font_size=16                  # 8 to 200
)
# Returns: {"rectangle_id": "...", "id": "...", "element_id": "...", "label_id": "..."}
```

### `create_connector`
Connects arbitrary canvas coordinates or binds two existing shapes with obstacle-avoiding orthogonal routing:

```python
connector = create_connector(
    source_id="rect_1",
    target_id="rect_2",
    label="publish(event)",
    elbowed=True,                 # True for orthogonal routing, False for straight arrow
    strokeStyle="dashed",
    strokeColor="#495057",
    strokeWidth=2
)
# Returns: {"arrow_id": "...", "id": "...", "element_id": "...", "label_id": "..."}
```

### `batch_mutate`
Executes multiple creation, styling, routing, and repair actions atomically in one turn with dynamic `client_id` resolution:

```python
result = batch_mutate(operations=[
    {
        "action": "add_frame",
        "client_id": "vpc",
        "name": "Cloud VPC",
        "x": 80, "y": 80, "w": 640, "h": 260
    },
    {
        "action": "add_rectangle",
        "client_id": "web",
        "x": 120, "y": 140, "w": 180, "h": 80,
        "label": "Web Frontend",
        "frame_id": "vpc",
        "backgroundColor": "#e7f5ff"
    },
    {
        "action": "add_rectangle",
        "client_id": "api",
        "x": 480, "y": 140, "w": 180, "h": 80,
        "label": "API Backend",
        "frame_id": "vpc",
        "backgroundColor": "#fff3bf"
    },
    {
        "action": "connect",
        "source_id": "web",
        "target_id": "api",
        "label": "HTTPS / JSON",
        "elbowed": True
    },
    {
        "action": "add_code_block",
        "x": 120, "y": 240,
        "code": "GET /healthz HTTP/1.1\nHost: api.internal",
        "language": "http",
        "theme": "dark"
    },
    {
        "action": "auto_fix_layout",
        "repair_scope": "all",
        "min_gap": 30.0
    }
])
# Returns: {"status": "applied", "operations_executed": 6, "results": [...], "revision": 2}
```

### `inspect_scene`
Unified query interface covering metrics, descriptions, search, and viewport status:

```python
# Semantic summary
summary = inspect_scene(mode="summary")

# Natural-language topological description for AI reasoning
description = inspect_scene(mode="describe", detailed=True)

# Search for specific elements
matches = inspect_scene(mode="find", query="Postgres", type="rectangle")

# Paginated element listing
elements_page = inspect_scene(mode="elements", offset=0, limit=20)
```

### `auto_fix_layout`
Layout repair engine with simulation mode and rollback protection:

```python
# Simulation mode: report defects without mutating active canvas
audit = auto_fix_layout(dry_run=True, repair_scope="all")

# Apply deterministic repairs across all phases
repair = auto_fix_layout(
    dry_run=False,
    repair_scope="all",             # "all" | "overlaps" | "connectors" | "containment" | "text" | "spacing"
    aggressiveness="balanced",      # "gentle" | "balanced" | "aggressive"
    min_gap=30.0,
    verbose=False                   # Return compact summary or verbose defect lists
)
```

### `preview`
Inline visual preview directly viewable in LLM turns:

```python
# Preview capped at 1568px (optimal vision envelope for Claude models)
preview(scale=1.0, padding=40, background=True, max_dimension=1568, format="png")
```

### `generate_diagram` (Full Profile)
Generates diagrams from Mermaid syntax, architecture DSL prompts, or Sugiyama graphs:

```python
# From Mermaid flowchart syntax
generate_diagram(
    format="mermaid",
    mermaid_code="""
    graph TD
        Client[Mobile App] --> APIGW[API Gateway]
        APIGW --> Auth[Auth Service]
        APIGW --> DB[(PostgreSQL)]
    """,
    direction="vertical",
    elbowed=True
)

# From rapid architectural sketch prompt
generate_diagram(
    format="architecture",
    prompt="box: Client Web App, box: API Gateway, circle: Redis Cache, db: Postgres Primary"
)
```
