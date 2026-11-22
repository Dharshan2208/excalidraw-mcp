<div align="center">

# Excalidraw MCP Server

**A headless, in-memory Model Context Protocol server enabling AI agents to programmatically generate, inspect, repair, and export native Excalidraw diagrams.**

[![License: MIT](https://img.shields.io/github/license/Dharshan2208/excalidraw-mcp?style=for-the-badge)](LICENSE)
[![PyPI Version](https://img.shields.io/pypi/v/exca-mcp?style=for-the-badge)](https://pypi.org/project/exca-mcp/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![CI Status](https://img.shields.io/github/actions/workflow/status/Dharshan2208/excalidraw-mcp/ci.yml?style=for-the-badge)](https://github.com/Dharshan2208/excalidraw-mcp/actions)
[![GitHub Stars](https://img.shields.io/github/stars/Dharshan2208/excalidraw-mcp?style=for-the-badge)](https://github.com/Dharshan2208/excalidraw-mcp/stargazers)

</div>

---

**Excalidraw MCP** is a backend-oriented Model Context Protocol (MCP) server that empowers AI coding agents to create, inspect, edit, diagnose, and export native [Excalidraw](https://excalidraw.com) diagrams over standard `stdio`.

Operating directly on scene graphs and element trees in memory with FreeType font metrics and topological collision solvers, it eliminates browser automation overhead to achieve sub-millisecond diagram mutations. All diagrams serialize strictly to Excalidraw Schema v2 JSON, guaranteeing immediate compatibility with excalidraw.com, IDE plugins, and high-resolution export pipelines.

---

## Visual Showcase

![Excalidraw MCP System Architecture](docs/architecture.png)
*System architecture diagram generated programmatically by Excalidraw MCP itself. Editable source: [docs/architecture.excalidraw](docs/architecture.excalidraw).*

---

## Key Features

- **Headless In-Memory Operations**: Operates 100% in pure Python on scene graphs in server memory with zero browser runtime or Node.js dependencies.
- **Native Excalidraw Schema v2**: Outputs fully valid, editable `.excalidraw` JSON documents compatible with [excalidraw.com](https://excalidraw.com).
- **Obstacle-Aware Orthogonal Routing**: Calculates Manhattan arrow paths around intervening shapes with 15 px clearance corridors and dynamic cardinal-face docking.
- **Parallel Multi-Edge Lanes**: Displaces parallel connectors between the same shapes into distinct 24 px lanes to prevent overlapping lines.
- **Font-Aware Text Metrics**: Uses FreeType and Pillow to measure exact typographic envelopes, preventing label clipping inside rectangles, rhombuses, and ellipses.
- **Automated Layout Repair (`auto_fix_layout`)**: Detects bounding box collisions, text clipping, and frame escapes, executing 5-phase de-collision and spacing with transactional regression rollback.
- **Atomic Batch Authoring (`batch_mutate`)**: Enables agents to create, move, style, connect, lock, group, and repair up to 500 operations in a single roundtrip with dynamic `client_id` resolution.
- **Halved Schema Context Footprint**: Minimalist tool contracts and compact minified JSON responses strip `outputSchema` overhead, reducing turn context usage by up to 50.4%.
- **High-Resolution Headless Export**: Headless Pillow rasterization generating PNG exports up to 8192 px, vector SVG exports, Obsidian Excalidraw plugin Markdown files (`.excalidraw.md`), and inline vision previews (`preview`) capped to optimal model envelopes (`max_dimension=1568`).
- **Interactive Live Canvas (`live_server`)**: Real-time Starlette/Uvicorn WebSocket visualizer streaming agent mutations live into an open browser tab.
- **Encrypted Web Sharing (`export_to_excalidraw_url`)**: Publishes scenes directly to excalidraw.com using 128-bit AES-GCM client-side encryption.
- **Bundled Agent Skills**: Packages 6 prompt and pattern guides covering architecture design, flowcharts, 60-30-10 color palettes, and quality gates, installable via `exca-mcp install-skills` (including automatic discovery for Claude Code via `exca-mcp install-skills --claude`).

---

## Quick Start

Run Excalidraw MCP instantly with [`uvx`](https://docs.astral.sh/uv/) (zero install required):

```bash
uvx exca-mcp
```

Or install via `pip`:

```bash
pip install exca-mcp
python -m excalidraw_mcp
```

---

## Installation

| Method | Command | Description |
|---|---|---|
| **uvx** *(Recommended)* | `uvx exca-mcp` | Zero-install ephemeral execution. |
| **pip** | `pip install exca-mcp` | Standard Python package installation. |
| **Docker** | `docker run -i --rm exca-mcp` | Containerized execution via stdio. |
| **Source** | `uv sync --locked && uv run exca-mcp` | Local clone for development. |

---

## MCP Client Configuration

Add Excalidraw MCP to your AI development environment:

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

> For configuration in OpenCode, Claude Code CLI, Gemini/Antigravity CLI, or Docker environments, see [docs/operations.md](docs/operations.md#extended-client-configurations).

---

## Toolset Overview (`core` vs `full`)

Excalidraw MCP provides two toolset profiles controlled by the `EXCALIDRAW_TOOLSET` environment variable:

| Profile | Tools | Context Overhead | Primary Capabilities |
|---|---:|---:|---|
| **`core`** *(default)* | **12** | **~5,048 tokens** | Primitives (`create_shape`, `create_connector`, `add_text`, `add_frame`), mutations (`update_element`, `delete`, `clear`, `undo`), atomic batches (`batch_mutate`), inspection (`inspect_scene`), layout repair (`auto_fix_layout`), and vision previews (`preview`). |
| **`full`** | **20** | **~7,937 tokens** | Includes all `core` tools plus file storage (`scene_storage`), disk export (`export_png`), generators (`generate_diagram`), element locking/grouping (`manage_element_state`), viewport framing (`set_viewport`), live browser sync (`live_server`), cloud sharing (`export_to_excalidraw_url`), and design rules (`read_diagram_guide`). |

To enable the complete 20-tool profile:

```bash
export EXCALIDRAW_TOOLSET=full
```

See [docs/tools.md](docs/tools.md) for the complete reference of all 20 tools, safety annotations, parameter schemas, and MCP resources.

---

## Minimal Usage Example

AI agents can construct, connect, repair, and preview diagrams using the default `core` toolset:

```python
# 1. Create container boundary frame
f = add_frame(name="Application Tier", x=100, y=100, w=600, h=220)

# 2. Add styled components inside the frame
s1 = create_shape(type="rectangle", x=140, y=160, w=180, h=90, label="API Gateway", frame_id=f["frame_id"], backgroundColor="#e7f5ff")
s2 = create_shape(type="rectangle", x=460, y=160, w=180, h=90, label="Auth Service", frame_id=f["frame_id"], backgroundColor="#fff3bf")

# 3. Connect components with an elbowed directional arrow
create_connector(source_id=s1["rectangle_id"], target_id=s2["rectangle_id"], label="verify_token()", elbowed=True)

# 4. Diagnose layout defects and render an inline visual preview
auto_fix_layout(dry_run=False, aggressiveness="balanced")
preview(max_dimension=1568, format="png")
```

For comprehensive end-to-end multi-tier cloud and flowchart workflows, see [docs/features.md](docs/features.md#end-to-end-workflow-examples).

---

## Documentation Index

| Guide | Description |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical architecture, subsystem request flow, state management, and geometry algorithms. |
| [docs/features.md](docs/features.md) | Detailed capability breakdown and end-to-end workflow examples. |
| [docs/tools.md](docs/tools.md) | Complete MCP tools reference, parameter schemas, code examples, resources, and task prompts. |
| [docs/auto-fix-layout.md](docs/auto-fix-layout.md) | 5-phase layout repair engine, parameters, visual comparisons, and rollback guarantees. |
| [docs/operations.md](docs/operations.md) | Environment variables reference, storage semantics, extended client configurations, and troubleshooting. |
| [docs/security.md](docs/security.md) | Security model, write sandboxing, live server origin protection, and cloud sharing encryption. |
| [docs/skills.md](docs/skills.md) | Packaged agent skills catalog, design guides, and CLI installer (`exca-mcp install-skills`). |
| [docs/graph-generation.md](docs/graph-generation.md) | Structured Sugiyama layered graph generation, ranking, and geometry rules. |
| [docs/migration_v030.md](docs/migration_v030.md) | Migration guide mapping all 48 legacy v0.2.x tools to v0.3.0 equivalents. |
| [CHANGELOG.md](CHANGELOG.md) | Version release history and migration notes. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer guide, test suite execution, and pull request guidelines. |
| [SECURITY.md](SECURITY.md) | Vulnerability disclosure procedures and policy. |

---

## Development & Contribution

```bash
# Clone the repository
git clone https://github.com/Dharshan2208/excalidraw-mcp.git
cd excalidraw-mcp

# Synchronize dependencies with uv
uv sync --locked

# Run the test suite (490 unit & contract tests)
uv run --locked python -B -m unittest discover -s tests -v

# Verify byte-compilation
uv run --locked python -B -m compileall -q -f excalidraw_mcp tests

# Validate package build
uv build
uvx twine check dist/*
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.


---

## License

This project is licensed under the [MIT License](LICENSE).




