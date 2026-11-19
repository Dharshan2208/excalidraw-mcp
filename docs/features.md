# Key Features & Capabilities

This document provides a comprehensive breakdown of the core features and capabilities provided by the Excalidraw MCP Server (`exca-mcp`).

---

## 1. High-Level Diagram Generation

- **Mermaid Support (`generate_diagram(format="mermaid")`)**: Convert standard Mermaid `flowchart` and `graph` syntax (including subgraphs, common node shapes, and edge labels) directly into native, editable Excalidraw elements.
- **Architecture Shorthand (`generate_diagram(format="architecture")`)**: Rapidly sketch multi-component architectures using simple comma- or newline-delimited prompts (e.g. `box: Frontend, db: Postgres, circle: Redis`).
- **Layered Graph Generator (`generate_diagram(format="graph")`)**: Programmatic hierarchical graph layout with topological ranking, clustered frame grouping, and edge routing.
- **Design Guidelines (`read_diagram_guide`)**: Built-in design guidance for agents covering 60-30-10 color palettes, dimensions, and visual hierarchy.

---

## 2. Primitive Elements & Composition

- **Geometric Primitives (`create_shape`)**: Rectangles, circles/ellipses, and diamonds with font-aware label containment and automatic centering.
- **Smart Connectors (`create_connector`)**: Directional arrows binding two shapes with cardinal-face docking ports, obstacle-avoiding orthogonal routing, and multi-edge parallel lane displacement.
- **Frames (`add_frame`)**: Container frames establishing visual and logical boundaries that group and move child elements hierarchically.
- **Standalone Text (`add_text`)**: Text elements measured using FreeType font metrics with selectable font families (Excalifont handwriting, sans-serif, monospace, Comic Shanns).
- **Code Blocks (`batch_mutate(operations=[{"action": "add_code_block", ...}])`)**: Syntax-highlighted code blocks with window chrome, line numbers, and theme options rendered directly on the canvas.
- **Atomic Operations (`batch_mutate`)**: Execute up to 500 creations, movements, stylings, connections, locks, and repairs in a single roundtrip with dynamic `client_id` resolution.

---

## 3. Automated Layout Repair (`auto_fix_layout`)

- **Defect Detection**: Identifies bounding box collisions, text clipping, frame containment escapes, and crowded node gaps.
- **5-Phase Repair Pipeline**: Executes container text clipping expansion, minimal-displacement de-collision, frame padding expansion, connector rerouting, and component spacing adjustments.
- **Simulation Mode (`dry_run=True`)**: Generates an actionable repair plan and defect inventory without mutating the active canvas.
- **Transactional Rollback Safety**: Automatically reverts mutations if a repair phase increases collisions or degrades layout geometry. See [docs/auto-fix-layout.md](auto-fix-layout.md).

---

## 4. Inspection, Persistence & Headless Export

- **Unified Scene Inspection (`inspect_scene`)**: Single entry point for high-level semantic summaries (`summary`), natural-language topological descriptions (`describe`), element searches (`find`), and paginated listings (`elements`).
- **Inline Agent Previews (`preview`)**: Generates base64 image previews directly into LLM turns with aspect-ratio dimension capping (`max_dimension=1568`) and selectable output formats (`png` or `jpeg`).
- **High-Resolution PNG Export (`export_png`)**: Headless Pillow rasterization supporting dynamic export dimensions up to 8192 px without a browser runtime.
- **Native Document Persistence (`scene_storage`)**: Atomically saves, loads, lists, exports, and imports complete Excalidraw Schema v2 JSON files (`.excalidraw`).
- **Client-Side Encrypted Sharing (`export_to_excalidraw_url`)**: Publishes scenes directly to excalidraw.com using 128-bit AES-GCM client-side encryption.

---

## 5. Interactive Live Canvas Server (`live_server`)

- **Real-Time Browser Sync**: Optional background Starlette/Uvicorn WebSocket visualizer streaming agent mutations into an open browser tab in real time.
- **Security Controls**: Protected via token authentication (`EXCALIDRAW_LIVE_TOKEN`), CSWSH origin validation, and remote interface binding restrictions (`EXCALIDRAW_ALLOW_REMOTE`). See [docs/security.md](security.md).

---

## 6. First-Class Agent Skills

- Six bundled engineering diagram skills installable via CLI (`exca-mcp install-skills`) and discoverable via MCP resources (`exca-mcp://skills/index`) and task prompts. See [docs/skills.md](skills.md).

---

## End-to-End Workflow Examples

### Workflow 1: Multi-Tier Cloud Architecture

```python
# 1. Establish logical tier container frames
f_ingress = add_frame(name="Tier 1: Edge & Ingress", x=100, y=100, w=1100, h=160)
f_services = add_frame(name="Tier 2: Core Microservices", x=100, y=300, w=1100, h=180)
f_data = add_frame(name="Tier 3: Persistence & Storage", x=100, y=520, w=1100, h=180)

# 2. Add components with semantic color palette (60-30-10 rule)
dns = create_shape(type="rectangle", x=140, y=140, w=220, h=80, label="Route 53 DNS", frame_id=f_ingress["frame_id"], backgroundColor="#f8f9fa")
alb = create_shape(type="rectangle", x=440, y=140, w=220, h=80, label="Application Load Balancer", frame_id=f_ingress["frame_id"], backgroundColor="#e7f5ff", strokeColor="#1971c2")

api = create_shape(type="rectangle", x=240, y=350, w=240, h=90, label="API Gateway Service\nNode.js / Express", frame_id=f_services["frame_id"], backgroundColor="#e7f5ff", strokeColor="#1971c2")
worker = create_shape(type="rectangle", x=620, y=350, w=240, h=90, label="Background Worker\nPython / Celery", frame_id=f_services["frame_id"], backgroundColor="#e7f5ff", strokeColor="#1971c2")

db = create_shape(type="rectangle", x=240, y=570, w=240, h=90, label="PostgreSQL Primary\nAmazon RDS", frame_id=f_data["frame_id"], backgroundColor="#e6fcf5", strokeColor="#0ca678")
redis = create_shape(type="rectangle", x=620, y=570, w=240, h=90, label="Redis Cache\nElastiCache Cluster", frame_id=f_data["frame_id"], backgroundColor="#fff9db", strokeColor="#f59f00")

# 3. Create bound, directional connectors with orthogonal routing
create_connector(source_id=dns["rectangle_id"], target_id=alb["rectangle_id"], label="HTTPS / 443", elbowed=True)
create_connector(source_id=alb["rectangle_id"], target_id=api["rectangle_id"], label="Forward", elbowed=True)
create_connector(source_id=api["rectangle_id"], target_id=db["rectangle_id"], label="SQL Read/Write", elbowed=True)
create_connector(source_id=api["rectangle_id"], target_id=redis["rectangle_id"], label="Cache Lookup", elbowed=True)
create_connector(source_id=worker["rectangle_id"], target_id=db["rectangle_id"], label="Batch Write", elbowed=True)

# 4. Auto-repair layout and preview
auto_fix_layout(dry_run=False, aggressiveness="balanced", min_gap=30.0)
preview(max_dimension=1568, format="png")
```

### Workflow 2: Logic Flowchart with Decision Diamonds & Perimeter Loops

```python
# 1. Start node (soft green rounded pill)
start = create_shape(type="rectangle", x=300, y=100, w=180, h=60, label="Start Deployment", roundness="round", backgroundColor="#e6fcf5", strokeColor="#0ca678")

# 2. Process step
build = create_shape(type="rectangle", x=300, y=210, w=180, h=70, label="Build Container Image", backgroundColor="#e7f5ff", strokeColor="#1971c2")

# 3. Explicit decision diamond
decision = create_shape(type="diamond", x=290, y=330, w=200, h=110, label="Smoke Tests Pass?", backgroundColor="#fff9db", strokeColor="#f59f00")

# 4. Distinct terminals
success = create_shape(type="rectangle", x=300, y=490, w=180, h=60, label="Deploy to Prod (Success)", roundness="round", backgroundColor="#ebfbee", strokeColor="#2b8a3e")
failed = create_shape(type="rectangle", x=580, y=355, w=180, h=60, label="Alert & Abort (Failed)", roundness="round", backgroundColor="#fff5f5", strokeColor="#c92a2a")

# 5. Connectors with explicit branch labels
create_connector(source_id=start["rectangle_id"], target_id=build["rectangle_id"], elbowed=True)
create_connector(source_id=build["rectangle_id"], target_id=decision["diamond_id"], elbowed=True)
create_connector(source_id=decision["diamond_id"], target_id=success["rectangle_id"], label="Yes", elbowed=True)
create_connector(source_id=decision["diamond_id"], target_id=failed["rectangle_id"], label="No", elbowed=True)

# 6. Repair and preview
auto_fix_layout(dry_run=False)
preview(max_dimension=1568)
```
