# Operations and Production Readiness

This document describes the operational architecture, configuration reference, storage semantics, client integrations, and production readiness guidelines for the Excalidraw MCP Server (`exca-mcp`).

---

## Process & Runtime Architecture

The server operates as an in-memory Model Context Protocol (MCP) server over standard input/output (`stdio`). Each running process maintains:
- Exactly one active working scene (`SceneState`) in process memory.
- Exactly one bounded undo/redo history snapshot stack.
- Zero mandatory background threads or persistent daemon requirements (unless the optional live server is launched).

Independent clients or workspace directories should launch separate server instances to ensure isolation.

---

## Configuration Reference

Configure server behavior using environment variables. When a variable is unset, the server applies safe defaults:

| Variable | Default | Valid Range / Format | Description |
|---|---|---|---|
| `EXCALIDRAW_TOOLSET` | `core` | `core`, `full` | Active toolset exposure profile. `core` exposes 12 essential tools (~3,133 tokens); `full` exposes all 21 tools (~5,628 tokens). |
| `EXCALIDRAW_TRANSPORT` | `stdio` | `stdio`, `streamable-http` | MCP server transport protocol. |
| `EXCALIDRAW_HOST` | `127.0.0.1` | IP address or hostname | Host interface for Streamable HTTP transport (never binds to 0.0.0.0 by default). |
| `EXCALIDRAW_PORT` | `8000` | `1` – `65535` | TCP port for Streamable HTTP transport. |
| `EXCALIDRAW_HTTP_PATH` | *Unset* | URL path (e.g. `/mcp`) | Custom endpoint path for Streamable HTTP transport. |
| `EXCALIDRAW_SCENE_DIR` | OS user data dir | Absolute path | Directory where `.excalidraw` JSON scene files are saved and loaded. |
| `EXCALIDRAW_EXPORT_DIR` | `EXCALIDRAW_SCENE_DIR/exports` | Absolute path | Target directory where PNG raster images are written. |
| `EXCALIDRAW_HISTORY_LIMIT` | `20` | `1` – `100` | Maximum number of in-memory undo snapshots retained. |
| `EXCALIDRAW_MAX_HISTORY_BYTES` | `104857600` (100MB) | `1024` – `524288000` | Maximum serialized byte budget for the in-memory undo stack. |
| `EXCALIDRAW_MAX_SCENE_BYTES` | `26214400` (25MB) | `1024` – `104857600` | Maximum allowable payload size when loading `.excalidraw` files. |
| `EXCALIDRAW_MAX_EXPORT_BYTES` | `26214400` (25MB) | `1024` – `104857600` | Maximum payload size returned by scene export operations. |
| `EXCALIDRAW_MAX_ELEMENTS` | `10000` | `1` – `100000` | Maximum element count allowed in an active scene. |
| `EXCALIDRAW_LIVE_PORT` | `8080` | `1024` – `65535` | Local TCP port for the live browser synchronization server. |
| `EXCALIDRAW_LIVE_TOKEN` | *Unset* | String | Optional shared secret token required for mutating live canvas requests. |
| `EXCALIDRAW_ALLOW_REMOTE` | *Unset* | `1`, `true` | Permits the live server to bind to non-loopback network interfaces (`0.0.0.0`). |
| `EXCALIDRAW_FONT_DIR` | *Unset* | Absolute path | Custom directory for TrueType/OpenType font discovery. |
| `EXCALIDRAW_DEFAULT_FONT` | `sans-serif` | Font family name | Default font family for shapes and standard text. |
| `EXCALIDRAW_MONO_FONT` | `monospace` | Font family name | Default font family for code blocks and monospace elements. |
| `EXCALIDRAW_SKILLS_DIR` | *Unset* | Absolute path | Custom override path for loading agent skill packages. |

### Default Storage Paths

When `EXCALIDRAW_SCENE_DIR` is not explicitly set, platform-standard user data locations are used:
- **Linux**: `$XDG_DATA_HOME/excalidraw-mcp/scenes` (fallback: `~/.local/share/excalidraw-mcp/scenes`)
- **macOS**: `~/Library/Application Support/excalidraw-mcp/scenes`
- **Windows**: `%APPDATA%\excalidraw-mcp\scenes`

---

## Storage & Persistence Semantics

1. **Atomic File Publication**: Scene saves (`scene_storage(action="save")`) write to a private temporary file first, invoke `fsync`, and publish via atomic rename.
2. **Directory Permissions**: New storage directories are created with private permissions (`0700`), and saved scene files use `0600`.
3. **Overwrite Safeguards**: Existing files are never replaced unless `overwrite=True` is explicitly specified.
4. **Filename Restrictions**: Scene names must strictly match `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`. Path separators, null bytes, parent references (`..`), and symlinks are rejected.
5. **Session Durability**: Working scenes exist in process memory. Undo history is trimmed by snapshot count and byte budget. To retain work across process restarts, save scenes explicitly via `scene_storage(action="save", name="...")`.

---

## Extended Client Configurations

### OpenCode

Add to `opencode.json` or `~/.config/opencode/config.json`:

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

### Claude Code CLI

Register with Claude Code:

```bash
claude mcp add excalidraw uvx exca-mcp
```

To configure with the full profile:

```bash
claude mcp add excalidraw -e EXCALIDRAW_TOOLSET=full uvx exca-mcp
```

### Google Antigravity / Gemini CLI

Add to root `mcp.json`:

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

### Docker Integration

Run containerized over stdio (`-i` interactive flag required for standard input):

```json
{
  "mcpServers": {
    "excalidraw": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "exca-mcp"]
    }
  }
}
```

---

## Live Canvas Server Operations

The `live_server` tool (available in `EXCALIDRAW_TOOLSET=full`) launches an in-process Starlette ASGI application running under Uvicorn in a background thread:

1. **Start Server**: `live_server(action="start", host="127.0.0.1", port=8080)`
2. **WebSocket Synchronization**: Connects to `ws://127.0.0.1:8080/ws` for real-time bidirectional scene delta streaming.
3. **Authentication**: If `EXCALIDRAW_LIVE_TOKEN` is set, connections require `?token=<token>` or `Authorization: Bearer <token>`.
4. **Stop Server**: `live_server(action="stop")` gracefully closes open WebSockets and terminates the server loop.

---

## Troubleshooting Guide

### 1. Tool Not Found: `generate_diagram`, `scene_storage`, or `live_server`
- **Cause**: The server defaults to `EXCALIDRAW_TOOLSET=core` (12 tools) to conserve token context.
- **Fix**: Set environment variable `EXCALIDRAW_TOOLSET=full` in your MCP client settings or shell.

### 2. PNG Export Path Validation Error
- **Cause**: Target directory is outside permitted paths.
- **Fix**: Export to `./exports`, `Path.cwd()`, or configure `EXCALIDRAW_EXPORT_DIR` with an absolute path.

### 3. Live Server Binding to 0.0.0.0 Denied
- **Cause**: The server blocks binding to `0.0.0.0` or external interfaces for security.
- **Fix**: Bind to `127.0.0.1` (default) or set `EXCALIDRAW_ALLOW_REMOTE=1` if remote access is required.

### 4. Font Rendering Fallback
- **Cause**: Excalifont or preferred system font is not installed on the system.
- **Fix**: Place TrueType fonts in a directory and set `EXCALIDRAW_FONT_DIR=/path/to/fonts`. The server automatically falls back gracefully to built-in font metrics.

---

## Quality Gate & Release Verification

Before tagging a release, run the quality checks:

```bash
uv lock --check
uv run --locked pytest tests/
uvx ruff check excalidraw_mcp tests
uv run --with mypy mypy excalidraw_mcp
uv run --locked python -B -m compileall -q -f main.py excalidraw_mcp tests
uv build
uvx twine check dist/*
```
