# Excalidraw MCP Server

<!-- TODO: mcp-name marker (server.json not found in repository) -->
[![PyPI version](https://img.shields.io/pypi/v/exca-mcp.svg)](https://pypi.org/project/exca-mcp/)
[![Python versions](https://img.shields.io/pypi/pyversions/exca-mcp.svg)](https://pypi.org/project/exca-mcp/)
[![CI status](https://github.com/Dharshan2208/excalidraw-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Dharshan2208/excalidraw-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/LICENSE)

A Model Context Protocol (MCP) server that enables AI agents to create, inspect, edit, and export diagrams in native [Excalidraw](https://excalidraw.com) format.

Built on FastMCP using Hatchling as the build backend. Diagrams are editable in standard Excalidraw tools and compatible with the Excalidraw Schema v2 format.

---

## Demo

![Excalidraw MCP System Architecture](https://raw.githubusercontent.com/Dharshan2208/excalidraw-mcp/main/docs/architecture.png)
*This diagram was generated with Excalidraw MCP itself. Editable file: [docs/architecture.excalidraw](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/docs/architecture.excalidraw).*

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

Excalidraw MCP includes an automated layout repair engine (`auto_fix_layout`) that detects and fixes overlaps, text clipping, and crowded nodes:

| Before Auto-Fix (Overlapping Nodes) | After Auto-Fix (Repaired Layout) |
|---|---|
| ![Before Auto-Fix](docs/images/before_autofix.png) | ![After Auto-Fix](docs/images/after_autofix.png) |

---

## What Excalidraw MCP Does

- **Generates native Excalidraw diagrams**: Generates valid Excalidraw Schema v2 JSON that can be opened and edited on [excalidraw.com](https://excalidraw.com) or in any Excalidraw client.
- **Renders Mermaid syntax**: Converts standard Mermaid `flowchart` and `graph` syntax into native Excalidraw diagram elements.
- **Maintains semantic connectivity**: Connects elements with smart arrows that track position and geometry changes dynamically.
- **Automates layout diagnostics and repair**: Detects overlaps, clipping, and crowding, repairing them in 5 topological phases with rollback safety.
- **Provides visual feedback to agents**: Generates inline image previews (`preview`) directly into LLM chats and exports high-resolution PNGs (`export_png`).
- **Supports real-time browser canvas sync**: Features an optional Starlette/WebSocket live server for observing diagram modifications live.

For a complete breakdown of capabilities, see [docs/features.md](docs/features.md).

---

## Architecture

The server consists of four primary internal subsystems:

1. **Protocol Layer (FastMCP)**: Exposes typed tools, resources, and task prompts over standard MCP stdio JSON-RPC.
2. **State & Transaction Engine (`SceneService`)**: Manages in-memory scene graphs, frame containment, spatial relationships, and process-local undo history.
3. **Geometric Computation Subsystems**:
   - `routing.py`: Cardinal face docking, obstacle clearance corridors, and parallel multi-edge lane assignment.
   - `text_padding.py` & `fonts.py`: Font metric measurement and inscribed text boundary constraints.
   - `auto_fix.py`: 5-phase layout diagnostics, displacement de-collision, and rollback safety.
4. **Rendering & Export Layer**: Headless Pillow rasterization, local filesystem persistence, and client-side encrypted URL sharing to excalidraw.com.

For full architectural details, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Installation

### Recommended: `uvx` (Zero Install)

Run the published PyPI package directly without manual dependency management:

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
docker build -t exca-mcp .
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

Excalidraw MCP bundles 6 specialized agent skills that teach AI assistants how to design professional diagrams:

| Skill | Focus |
|---|---|
| `diagram-planning` | Entry-tool decision tree and canvas preparation. |
| `architecture-diagrams` | Cloud, distributed system, and tiered system architectures. |
| `flowcharts-and-processes` | Decision trees, workflow diagrams, and state machines. |
| `human-style-and-polish` | 60-30-10 color palettes, typography, and spacing conventions. |
| `verify-and-editable-handoff` | Quality verification, overlap checks, and export handoff. |
| `excalidraw-workflow` | End-to-end multi-step diagram composition lifecycle. |

### Installing Skills into Your Project

Use the bundled CLI installer to install skills into your AI workspace:

```bash
# Preview available skills
uvx exca-mcp install-skills --list

# Install skills into your project .skills/ directory
uvx exca-mcp install-skills --target .skills
```

Skills are also directly discoverable by connected MCP clients via `excalidraw://skills` resources. See [docs/skills.md](docs/skills.md).

---

## Toolset Overview

The server provides two toolset profiles controlled by the `EXCALIDRAW_TOOLSET` environment variable:
- **`core` (default, 27 tools)**: Standard creation, mutation, inspection, auto-repair, and export tools. Optimizes context efficiency by reducing schema overhead by 45.2% (~6,560 tokens per turn).
- **`full` (48 tools)**: Includes all core tools plus `draw_graph`, `batch_mutate`, element locking, grouping, camera viewport controls, and the live canvas server.

To enable the full toolset:
```bash
export EXCALIDRAW_TOOLSET=full
```

For the complete reference of all tools, arguments, and return schemas, see [docs/tools.md](docs/tools.md).

---

## Common Workflows

### 1. Generating Flowcharts from Mermaid
Agents can render existing Mermaid markup directly into editable Excalidraw scenes:
```python
draw_mermaid(mermaid_code="""
graph TD
    Client[Client App] --> Gateway[API Gateway]
    Gateway --> Auth[Auth Service]
    Gateway --> Orders[Order Service]
    Orders --> DB[(PostgreSQL)]
""")
```

### 2. Sketching Rapid Architectures
```python
draw_architecture(prompt="box: Web App, box: API Gateway, circle: Cache, db: Database")
```

### 3. Diagnosing and Auto-Fixing Layouts
```python
# Check for layout defects without applying changes
report = auto_fix_layout(dry_run=True)

# Apply transactional layout repair
auto_fix_layout(dry_run=False)
```

See [docs/auto-fix-layout.md](docs/auto-fix-layout.md) for full details on the 5-phase repair engine.

---

## Configuration

Configure server behavior using environment variables:

| Variable | Default | Description |
|---|---|---|
| `EXCALIDRAW_TOOLSET` | `core` | Toolset exposure profile: `core` (27 tools) or `full` (48 tools). |
| `EXCALIDRAW_SCENE_DIR` | `.excalidraw` | Storage directory for saved `.excalidraw` scenes. |
| `EXCALIDRAW_EXPORT_DIR` | `./exports` | Target directory for PNG image exports. |
| `EXCALIDRAW_HISTORY_LIMIT` | `50` | Maximum undo snapshots retained in memory. |
| `EXCALIDRAW_MAX_HISTORY_BYTES` | `52428800` (50MB) | Maximum memory allocated to the undo history stack. |
| `EXCALIDRAW_MAX_DOCUMENT_BYTES`| `5242880` (5MB) | Maximum size allowed for loaded scene documents. |
| `EXCALIDRAW_MAX_EXPORT_BYTES`  | `10485760` (10MB) | Maximum payload size for scene export operations. |
| `EXCALIDRAW_LIVE_PORT` | `8080` | Port for the live canvas browser server. |
| `EXCALIDRAW_LIVE_TOKEN` | *Unset* | Shared secret required for mutating live canvas endpoints. |
| `EXCALIDRAW_ALLOW_REMOTE` | `false` | When true, permits live server binding to non-loopback interfaces. |

---

## Live Canvas Server

The server includes an optional browser canvas server (`start_live_server`) that syncs mutations to an interactive web canvas via WebSockets:

1. Agent calls `start_live_server(port=8080)`.
2. Open `http://localhost:8080` in any web browser.
3. Every tool call updating the diagram reflects immediately on the live canvas.

See [docs/security.md](docs/security.md) for authentication and origin configuration.

---

## Security

Excalidraw MCP implements strict boundaries to protect local environments:
- **Write Sandboxing**: `save` is confined strictly to `EXCALIDRAW_SCENE_DIR`. `export_png` writes only to allowed export roots (`export_directory`, `scene_directory`, `Path.cwd()`, or tempdir). Path traversal (`..`) and symlink escapes are rejected.
- **Authentication**: Live server mutating endpoints support token authentication (`EXCALIDRAW_LIVE_TOKEN`).
- **Origin Validation**: Live WebSocket server protects against Cross-Site WebSocket Hijacking (CSWSH).
- **Interface Guard**: Binding to `0.0.0.0` is blocked unless `EXCALIDRAW_ALLOW_REMOTE=true` is set.

Report security vulnerabilities via our [Security Policy](SECURITY.md) and [GitHub Security Advisories](https://github.com/Dharshan2208/excalidraw-mcp/security/advisories/new).

---

## Limitations

- **Mermaid Support**: `draw_mermaid` supports `flowchart` and `graph` syntax (including subgraphs, common shapes, and links). Other diagram types (sequence diagrams, state diagrams, class diagrams, ER diagrams) are not supported.
- **Process Local State**: The scene is stored in server memory. Restarting the MCP server resets the unsaved active scene; use `save(name=...)` to persist work.
- **Export Formats**: Headless export generates native `.excalidraw` JSON and PNG raster images. Direct SVG export without a browser runtime is not currently supported.

---

## Troubleshooting

### Tool Not Found Errors (`draw_graph`, `batch_mutate`, etc.)
- **Cause**: The server defaults to the `core` toolset (27 tools).
- **Solution**: Set `EXCALIDRAW_TOOLSET=full` in your MCP client configuration environment variables.

### PNG Export Validation Errors
- **Cause**: Target export path is outside permitted directories.
- **Solution**: Export to `./exports`, the current working directory, or configure `EXCALIDRAW_EXPORT_DIR`.

### Live Canvas Remote Access Denied
- **Cause**: Server refused binding to an external network interface.
- **Solution**: Live server binds to `127.0.0.1` by default. Set `EXCALIDRAW_ALLOW_REMOTE=true` to permit external interface binding.

---

## Development

```bash
# Clone repository
git clone https://github.com/Dharshan2208/excalidraw-mcp.git
cd excalidraw-mcp

# Install dependencies with uv
uv sync --all-extras

# Run tests
uv run --locked python -B -m unittest discover -s tests -v

# Validate package build
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contribution guidelines.

---

## Documentation Index

- [docs/tools.md](docs/tools.md): Complete MCP tools reference, arguments, and return types.
- [docs/features.md](docs/features.md): Detailed capability guide.
- [docs/auto-fix-layout.md](docs/auto-fix-layout.md): 5-phase automated layout repair engine.
- [docs/skills.md](docs/skills.md): Agent skills distribution and CLI installer.
- [docs/security.md](docs/security.md): Security guide, write confinement, and live server protections.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): Subsystem architecture and transaction design.
- [CHANGELOG.md](CHANGELOG.md): Project release history and breaking changes.
- [SECURITY.md](SECURITY.md): Vulnerability reporting policy.

---

## License

This project is licensed under the [MIT License](https://github.com/Dharshan2208/excalidraw-mcp/blob/main/LICENSE).
