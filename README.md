# Excalidraw MCP Server

<!-- TODO: mcp-name marker (server.json not found in repository) -->
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyPI](https://img.shields.io/pypi/v/exca-mcp.svg)](https://pypi.org/project/exca-mcp/)
[![FastMCP](https://img.shields.io/badge/FastMCP-2.0%2B-green.svg)](https://github.com/jlowin/fastmcp)
[![CI](https://github.com/Dharshan2208/excalidraw-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Dharshan2208/excalidraw-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/LICENSE)
[![Built with Hatchling](https://img.shields.io/badge/build-hatchling-purple.svg)](https://hatch.pypa.io/)

Excalidraw MCP is a backend-oriented Model Context Protocol (MCP) server that enables AI agents to create, inspect, edit, diagnose, and export native [Excalidraw](https://excalidraw.com) diagrams over standard `stdio`.

Unlike browser-automation wrappers, Excalidraw MCP operates directly on scene graphs and element trees in memory. AI coding agents can construct complex architectures, generate flowcharts from Mermaid syntax, inspect element hierarchies, and apply deterministic layout repairs without requiring a running web browser or graphical interface.

Diagrams are serialized in native Excalidraw Schema v2 format, ensuring immediate compatibility with excalidraw.com, standard Excalidraw desktop extensions, and headless image export pipelines.

---

## Demo

![Excalidraw MCP System Architecture](https://raw.githubusercontent.com/Dharshan2208/excalidraw-mcp/main/docs/architecture.png)
*This diagram was generated with Excalidraw MCP itself. Editable source: [docs/architecture.excalidraw](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/docs/architecture.excalidraw).*

<details>
<summary>View agent generation workflow and tool calls</summary>

```python
# 1. Create architectural tier frames
f1 = add_frame(name="Tier 1 — Clients & Host Environments", x=100, y=100, w=1560, h=140)
f2 = add_frame(name="Tier 2 — Protocol Gateways & Security Edge", x=100, y=280, w=1560, h=150)
f3 = add_frame(name="Tier 3 — Application Core & Transaction Orchestrator", x=100, y=470, w=1560, h=160)
f4 = add_frame(name="Tier 4 — Layout, Routing & Geometry Subsystems", x=100, y=670, w=1560, h=160)
f5 = add_frame(name="Tier 5 — Rendering, Export & Cloud Integration", x=100, y=870, w=1560, h=160)
f6 = add_frame(name="Tier 6 — Persistence & File System Layer", x=100, y=1070, w=1560, h=160)

# 2. Add component boxes within tier frames
c1 = add_rectangle(x=140, y=130, w=320, h=80, label="AI Coding IDEs & Agents\nClaude Desktop • Cursor • Zed", frame_id=f1["id"], backgroundColor="#e3fafc")
c2 = add_rectangle(x=540, y=130, w=320, h=80, label="Agent CLI & Automation Runners\nCodex CLI • FastMCP Inspector", frame_id=f1["id"], backgroundColor="#e3fafc")
s1 = add_rectangle(x=140, y=310, w=380, h=90, label="FastMCP Protocol Server (stdio)\nJSON-RPC 2.0 Transport • Schema Validation", frame_id=f2["id"], backgroundColor="#fff3bf")
s2 = add_rectangle(x=580, y=310, w=360, h=90, label="Security & Origin Firewall Guard\nEXCALIDRAW_LIVE_TOKEN • CSWSH Origin Guard", frame_id=f2["id"], backgroundColor="#fff3bf")

# 3. Connect components with labeled connectors
connect(from_id=c1["id"], to_id=s1["id"], label="stdio JSON-RPC", elbowed=True)
connect(from_id=c2["id"], to_id=s1["id"], label="stdio JSON-RPC", elbowed=True)
connect(from_id=s1["id"], to_id=s2["id"], label="Validation Pipeline", elbowed=True)

# 4. Run automated layout repair and export
auto_fix_layout(dry_run=False)
export_png(name="architecture", directory="docs", scale=2.0)
save(name="architecture")
```
</details>

### Automated Layout Repair Preview

Excalidraw MCP includes an automated layout repair engine (`auto_fix_layout`) that detects and repairs overlaps, text clipping, and crowded nodes:

| Before Auto-Fix (Overlapping Nodes) | After Auto-Fix (Repaired Layout) |
|---|---|
| ![Before Auto-Fix](docs/images/before_autofix.png) | ![After Auto-Fix](docs/images/after_autofix.png) |

---

## Key Features

### A. Intelligent Diagram Generation
- **Native Schema v2 Serialization**: Generates valid Excalidraw JSON documents that open directly in Excalidraw without conversion.
- **Mermaid Conversion (`draw_mermaid`)**: Parses Mermaid `flowchart` and `graph` syntax (`TD`, `TB`, `LR`, `RL`, `BT`) with node shapes, subgraphs, and edge labels.
- **Shorthand Architecture Generation (`draw_architecture`)**: Rapidly parses comma- and newline-delimited component lists with automatic grid-wrapping.
- **Semantic Arrow Binding (`connect`)**: Creates smart directional connectors with start/end element bindings that stay connected when shapes move or resize.

### B. Advanced Layout and Geometry
- **Obstacle-Aware Orthogonal Routing**: Calculates Manhattan paths around intermediate bounding boxes with 15 px obstacle clearance corridors.
- **Cardinal-Face Port Attachment**: Dynamically calculates dock points and surface normal vectors on the top, bottom, left, and right faces of rectangles, ellipses, and diamonds.
- **Multi-Edge Parallel Lane Assignment**: Displaces parallel connectors between the same shapes into distinct lanes (24 px spacing) to eliminate line overlaps.
- **Collision-Free Label Placement**: Positions connector labels along unobstructed route segments away from intersecting nodes.
- **Font-Aware Text Metrics**: Accurately measures text dimensions and character envelopes using FreeType and Pillow.
- **Font Support**: Supports Excalidraw standard font families: Excalifont (handwriting), sans-serif (Helvetica), monospace (Cascadia), and Comic Shanns.
- **Inscribed Polygon Boundary Containment**: Enforces geometric containment math for labels inside rhombuses and ellipses.
- **Two-Pass Architecture Layout**: Measures all components in pass 1, then computes wrapped rows and frame boundaries in pass 2.

### C. Automated Diagnostics and Layout Repair
- **Geometric Defect Detection**: Detects bounding box collisions, text clipping, frame containment escapes, and crowded node gaps.
- **Automated Repair Engine (`auto_fix_layout`)**: Executes targeted geometry repairs across five deterministic phases:
  1. Container text clipping expansion outward from center.
  2. Minimal-displacement de-collision with grouping preservation.
  3. Frame boundary containment padding expansion.
  4. Obstacle-aware connector rerouting.
  5. Component spacing adjustments for crowded nodes.
- **Simulation Mode (`dry_run=True`)**: Generates an actionable repair plan and defect inventory without mutating the active canvas.
- **Transactional Rollback Safety**: Reverts mutations automatically if a repair phase increases collisions or degrades layout geometry.

### D. Rendering and Export
- **Dynamic Canvas Dimensioning**: Computes exact bounding hulls for active scenes with configurable padding.
- **High-Resolution PNG Export (`export_png`)**: Headless Pillow rasterization supporting dynamic export dimensions up to 8192 px.
- **Inline Agent Previews (`preview`)**: Generates base64-encoded PNG previews directly into LLM chat turns without writing to disk.
- **Native Document Persistence (`save`)**: Atomically writes complete `.excalidraw` JSON files to configured scene storage.
- **Headless Rasterization**: Full raster export and preview rendering without browser runtimes, Node.js, or external CLI dependencies.

### E. Agent and Tooling Optimization
- **Two-Tier Toolset Profiles**: Supports `core` (27 tools) and `full` (48 tools) profiles via the `EXCALIDRAW_TOOLSET` environment variable.
- **Context Overhead Reduction**: The default `core` profile saves 45.2% in schema tokens (~6,560 tokens per turn) compared to the full set.
- **Zero-Token Capability Discovery**: MCP resource `excalidraw://capabilities` provides machine-readable tool catalogs without consuming LLM context.
- **Six Bundled Agent Skills**: Packaged prompt and pattern guides teach agents optimal color palettes, spacing rules, and diagram workflows.
- **Fast Onboarding**: Direct execution via `uvx exca-mcp` and root-level `mcp.json` support.

### F. Interactive Canvas and Element Management
- **Background Live Canvas Server (`start_live_server`)**: Optional Starlette and WebSocket engine serving an interactive web visualizer.
- **Real-Time Browser Sync**: Live bidirectional WebSocket updates synchronize agent tool mutations to browser tabs in real time.
- **Element Locking (`set_element_locked`)**: Protects background frames, watermarks, or finished tiers from accidental manipulation.
- **Logical Grouping (`manage_groups`)**: Groups and ungroups related components to preserve layout structure during manual edits.
- **Camera Viewport Controls (`set_viewport`)**: Programmatically sets canvas coordinates, zoom scale, background color, or auto-frames specific elements.
- **Syntax-Highlighted Code Blocks (`add_code_block`)**: Renders monospace code blocks with mac-style window chrome, line numbers, and theme options.

### G. Reliability and Security
- **Atomic File Operations**: Persisted scenes and exported images use temporary files and atomic rename operations.
- **Process-Local Undo Stack (`undo`)**: Reverts mutations across a bounded history stack (`EXCALIDRAW_HISTORY_LIMIT` snapshots).
- **Client-Side Encrypted Sharing (`export_to_excalidraw_url`)**: Generates shareable excalidraw.com links using client-side AES-GCM encryption.
- **Filesystem Write Sandboxing**: Confinements enforce writes strictly within configured scene and export directories.
- **Live Server Token Authentication**: Protects live canvas mutations via `EXCALIDRAW_LIVE_TOKEN` shared secrets.
- **CSWSH Origin Validation**: Restricts live server WebSocket connections to localhost, 127.0.0.1, and excalidraw.com.

For full feature documentation, see [docs/features.md](docs/features.md).

---

## Architecture

```
                  +----------------------------------------------+
                  |         AI Coding Assistants & Hosts         |
                  |     (Claude Desktop, Cursor, Zed, OpenCode)  |
                  +----------------------+-----------------------+
                                         | stdio (JSON-RPC 2.0)
                                         v
+---------------------------------------------------------------------------------+
| FastMCP Protocol Layer                                                          |
| - Tool Routing (27 Core / 48 Full tools via EXCALIDRAW_TOOLSET)                 |
| - Schema Validation & Resource Endpoints (excalidraw://capabilities, skills)    |
+----------------------------------------+----------------------------------------+
                                         |
                                         v
+---------------------------------------------------------------------------------+
| State & Transaction Engine (SceneService)                                       |
| - In-Memory Scene Graph (SceneState) & Element Remapping                        |
| - Bounded History Stack (undo) & Monotonic Revisions                            |
+-------------------+-------------------------------------+-----------------------+
                    |                                     |
                    v                                     v
+-----------------------------------+   +-----------------------------------------+
| Geometric Computation Subsystems  |   | Rendering, Persistence & Live Sync      |
| - routing.py: Obstacle Corridors  |   | - renderer.py: Pillow Rasterization     |
| - text_padding.py: Dynamic Bounds |   | - scene.py: Atomic POSIX Save/Load    |
| - fonts.py: FreeType Metrics      |   | - sharing.py: Client-Side AES-GCM URLs  |
| - auto_fix.py: 5-Phase Repair     |   | - live_server.py: Starlette & WebSocket |
+-----------------------------------+   +-----------------------------------------+
```

The server architecture consists of four primary internal subsystems:

1. **Protocol Layer (`FastMCP`)**: Exposes strictly typed tools, resources, and task prompts over standard MCP `stdio`. Exposes either the 27-tool `core` or 48-tool `full` profile based on `EXCALIDRAW_TOOLSET`.
2. **State & Transaction Engine (`SceneService`)**: Maintains active elements, frame parent-child hierarchies, and a bounded undo stack (`EXCALIDRAW_HISTORY_LIMIT`) in memory with monotonic revision counters.
3. **Geometric Computation Subsystems**:
   - [`routing.py`](excalidraw_mcp/routing.py): Computes cardinal-face ports, 15 px obstacle avoidance corridors, and 24 px parallel multi-lane connector paths.
   - [`text_padding.py`](excalidraw_mcp/text_padding.py) & [`fonts.py`](excalidraw_mcp/fonts.py): Font metric measurement, word wrapping, and inscribed rhombus/ellipse text containment.
   - [`auto_fix.py`](excalidraw_mcp/auto_fix.py): Five-phase topological layout diagnostic and repair engine with automatic regression rollback.
4. **Rendering and Persistence Layer**:
   - [`renderer.py`](excalidraw_mcp/renderer.py): Headless Pillow rasterization generating PNG exports up to 8192 px and inline base64 image previews.
   - [`scene.py`](excalidraw_mcp/scene.py): Confined, atomic scene persistence in native Excalidraw Schema v2 format.
   - [`sharing.py`](excalidraw_mcp/sharing.py): Client-side AES-GCM encrypted URL generation for direct sharing to excalidraw.com.
   - [`live_server.py`](excalidraw_mcp/live_server.py): Background Starlette/Uvicorn server providing real-time WebSocket synchronization to an interactive browser canvas.

For deep subsystem implementation details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Installation

### Recommended: `uvx` (Zero Install)

Run the published PyPI package instantly in an ephemeral, isolated environment using [`uvx`](https://docs.astral.sh/uv/):

```bash
uvx exca-mcp
```

### Alternative: `pip`

Install into a Python 3.10+ virtual environment:

```bash
pip install exca-mcp
python -m excalidraw_mcp
```

### Alternative: Docker

Build and run the container locally via standard input/output:

```bash
# Build the Docker container locally
docker build -t exca-mcp .

# Run the server via standard I/O (interactive mode -i is required for MCP stdio)
docker run -i --rm exca-mcp
```

---

## Client Configuration

Configure Excalidraw MCP in your AI development environment:

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "uvx",
      "args": ["exca-mcp"]
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` or Global MCP Settings:

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "uvx",
      "args": ["exca-mcp"]
    }
  }
}
```

### Zed

Add to `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "excalidraw": {
      "command": {
        "path": "uvx",
        "args": ["exca-mcp"]
      }
    }
  }
}
```

### OpenCode

Add to `opencode.json`:

```json
{
  "mcp": {
    "excalidraw": {
      "type": "local",
      "command": ["uvx", "exca-mcp"]
    }
  }
}
```

---

## Agent Skills

Excalidraw MCP packages six specialized agent skills that guide AI coding models on color harmony, spatial hierarchy, and diagram construction:

| Skill | Description | Key Topics |
|---|---|---|
| `diagram-planning` | Upfront planning and entry-tool decision tree. | Diagram classification, audience targeting, layout tiering, entry tool selection. |
| `architecture-diagrams` | Cloud, distributed systems, and backend design. | Multi-tier frames, ingress/egress boundaries, side columns, explicit protocol bindings. |
| `flowcharts-and-processes` | Process flows, logic pipelines, and state machines. | Single start/terminals, decision diamonds, labeled branches, perimeter retry loops. |
| `human-style-and-polish` | Excalidraw hand-drawn aesthetics and polish. | 60-30-10 palette rule, stroke weights, typography scale, geometric clearances. |
| `verify-and-editable-handoff` | Defect verification and dual-format delivery. | `auto_fix_layout` diagnostics, PNG visual review, human editability checks. |
| `excalidraw-workflow` | End-to-end diagram construction lifecycle. | Initialization, multi-tier layout, routing, verification, and persistence. |

### Installing Skills into Your Project

Use the bundled CLI installer to install packaged skills into your project workspace:

```bash
# List all packaged skills and reference guides
uvx exca-mcp install-skills --list

# Install skills into your project-local .skills directory
uvx exca-mcp install-skills --target .skills
```

Skills are also directly accessible to MCP clients via the `exca-mcp://skills/index` and `exca-mcp://skills/{name}` resources. See [docs/skills.md](docs/skills.md).

---

## Toolset Overview

The server provides two toolset profiles controlled by the `EXCALIDRAW_TOOLSET` environment variable:

| Profile | Tools | Description |
|---|---:|---|
| `core` | 27 | Streamlined default toolset covering creation, manipulation, inspection, layout repair, and export. |
| `full` | 48 | Complete toolset adding `draw_graph`, `batch_mutate`, element locking, grouping, camera viewports, and the live server. |

The `core` toolset reduces JSON Schema overhead by 45.2% (~6,560 tokens per turn), leaving more context available for agent reasoning.

To enable the complete 48-tool set:

```bash
export EXCALIDRAW_TOOLSET=full
```

For the complete reference of all tools, arguments, and return types, see [docs/tools.md](docs/tools.md).

---

## Common Workflows

### 1. Generating Flowcharts from Mermaid Syntax
Convert existing Mermaid flowchart syntax into native Excalidraw elements:

```python
draw_mermaid(
    mermaid_code="""
    graph TD
        Client[Web Client] --> Gateway[API Gateway]
        Gateway --> Auth[Auth Service]
        Gateway --> Orders[Order Service]
        Orders --> DB[(PostgreSQL)]
    """,
    direction="TD",
    elbowed=True
)
```

### 2. Sketching Systems Using Architecture Shorthand
Rapidly sketch multi-component system architectures:

```python
draw_architecture(
    prompt="box: Client Web App, box: API Gateway, circle: Redis Cache, db: Postgres Database",
    wrap_threshold=3
)
```

### 3. Diagnosing Layout Defects with Dry-Run
Preview layout defects (overlaps, text clipping, and crowding) without mutating the canvas:

```python
# Returns an AutoFixLayoutResult report of detected issues and planned repairs
report = auto_fix_layout(dry_run=True, repair_scope="all")
```

### 4. Applying Layout Repairs with Rollback Safety
Execute the five-phase repair engine to resolve overlaps and adjust spacing:

```python
# Applies repairs atomically with automatic rollback if regressions occur
result = auto_fix_layout(dry_run=False, aggressiveness="balanced", min_gap=30.0)
```

For full details on the layout repair engine, see [docs/auto-fix-layout.md](docs/auto-fix-layout.md).

---

## Configuration

Configure server behavior using environment variables:

| Variable | Default | Valid Range / Format | Description |
|---|---|---|---|
| `EXCALIDRAW_TOOLSET` | `core` | `core`, `full` | Active toolset exposure profile. |
| `EXCALIDRAW_SCENE_DIR` | OS user data dir | Absolute path | Directory where `.excalidraw` scenes are saved. |
| `EXCALIDRAW_EXPORT_DIR` | `EXCALIDRAW_SCENE_DIR/exports` | Absolute path | Target directory for PNG image exports. |
| `EXCALIDRAW_HISTORY_LIMIT` | `20` | `1` – `100` | Maximum undo snapshots retained in memory. |
| `EXCALIDRAW_MAX_HISTORY_BYTES` | `104857600` (100MB) | `1024` – `524288000` | Memory budget for the serialized undo stack. |
| `EXCALIDRAW_MAX_SCENE_BYTES` | `26214400` (25MB) | `1024` – `104857600` | Maximum file size accepted when loading scenes. |
| `EXCALIDRAW_MAX_EXPORT_BYTES` | `26214400` (25MB) | `1024` – `104857600` | Maximum payload size for scene export operations. |
| `EXCALIDRAW_MAX_ELEMENTS` | `10000` | `1` – `100000` | Maximum elements allowed per scene. |
| `EXCALIDRAW_LIVE_PORT` | `8080` | `1024` – `65535` | Port for the live canvas browser server. |
| `EXCALIDRAW_LIVE_TOKEN` | *Unset* | String | Shared secret required for mutating live canvas requests. |
| `EXCALIDRAW_ALLOW_REMOTE` | *Unset* | `1`, `true` | Permits live canvas binding to non-loopback interfaces. |
| `EXCALIDRAW_FONT_DIR` | *Unset* | Absolute path | Custom directory for TrueType/OpenType font discovery. |

---

## Live Canvas Server

The server includes an optional live canvas server (`start_live_server`, available in the `full` toolset) that synchronizes scene mutations to an interactive browser window in real time:

1. Enable the full toolset: `export EXCALIDRAW_TOOLSET=full`.
2. Agent invokes `start_live_server(host="127.0.0.1", port=8080)`.
3. Open `http://localhost:8080` in a browser.
4. Diagram mutations performed by the agent appear in real time over WebSockets.

See [docs/security.md](docs/security.md) for live server authentication and network guards.

---

## Security

Excalidraw MCP implements strict boundaries to protect local environments:

- **Filesystem Write Sandboxing**: `save` is confined strictly to `EXCALIDRAW_SCENE_DIR`. `export_png` writes only to allowed roots (`export_directory`, `scene_directory`, `Path.cwd()`, or `tempfile.gettempdir()`). Path traversal (`..`) and symlink escapes are rejected.
- **Skill Installer Security**: `exca-mcp install-skills` rejects installation to the system root (`/`) and blocks symlink traversal.
- **Token Authentication (`EXCALIDRAW_LIVE_TOKEN`)**: When configured, live canvas mutations via REST (`POST /api/scene`) and WebSocket connections (`/ws`) require token verification.
- **CSWSH Origin Defense**: The WebSocket live server rejects connections originating from untrusted web origins.
- **Interface Guard (`EXCALIDRAW_ALLOW_REMOTE`)**: Binding the live server to `0.0.0.0` or external interfaces is blocked unless explicitly enabled.

For security guidelines or vulnerability reporting, see [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md).

---

## Limitations

- **Mermaid Syntax Scope**: `draw_mermaid` supports `flowchart` and `graph` syntax (including subgraphs, common node shapes, and edge labels). Other Mermaid diagrams (sequence, class, state, ER, Gantt) are not supported.
- **Process-Local Memory**: Active scenes reside in server memory. If the MCP server process restarts, unsaved scenes reset; call `save(name=...)` to persist scenes to disk.
- **Export Formats**: Headless export produces native `.excalidraw` JSON and PNG images. Direct SVG export without a browser runtime is not currently supported.
- **Live Canvas Toolset**: Live canvas sync (`start_live_server`) requires `EXCALIDRAW_TOOLSET=full`.

---

## Troubleshooting

### Tool Not Found Errors (`draw_graph`, `batch_mutate`, `start_live_server`)
- **Cause**: The server defaults to the `core` profile (27 tools) for token efficiency.
- **Solution**: Set `EXCALIDRAW_TOOLSET=full` in your MCP client environment configuration.

### PNG Export Validation Errors
- **Cause**: Target export directory is outside permitted paths.
- **Solution**: Export to `./exports`, `Path.cwd()`, or configure `EXCALIDRAW_EXPORT_DIR` with an absolute path.

### Live Canvas Remote Connection Denied
- **Cause**: Server blocked binding to `0.0.0.0` for security.
- **Solution**: Use `127.0.0.1` (default) or set `EXCALIDRAW_ALLOW_REMOTE=1` if remote access is required.

---

## Development

```bash
# Clone the repository
git clone https://github.com/Dharshan2208/excalidraw-mcp.git
cd excalidraw-mcp

# Synchronize dependencies with uv
uv sync --all-extras

# Run the full unit test suite
uv run --locked python -B -m unittest discover -s tests -v

# Verify source compilation
python -m compileall excalidraw_mcp tests

# Validate package distribution
uv build
uvx twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development and contribution guidelines.

---

## Documentation Index

- [docs/tools.md](docs/tools.md): Complete reference of all 48 tools, signatures, and schemas.
- [docs/features.md](docs/features.md): Comprehensive capability and feature breakdown.
- [docs/auto-fix-layout.md](docs/auto-fix-layout.md): Five-phase layout repair engine, parameters, and rollback guarantees.
- [docs/skills.md](docs/skills.md): Agent skills catalog, reference guides, and installer instructions.
- [docs/security.md](docs/security.md): Security guide, write sandboxing, and live server protections.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Technical deep dive into subsystem architecture and geometry algorithms.
- [CHANGELOG.md](CHANGELOG.md): Project release history and version migration notes.
- [SECURITY.md](SECURITY.md): Security policy and vulnerability disclosure procedures.

---

## License

This project is licensed under the [MIT License](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/LICENSE).
