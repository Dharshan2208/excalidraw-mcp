# Security Guide

This document describes the security model, configuration, and controls for the Excalidraw MCP Server (`exca-mcp`).

## Protocol Security & Execution Boundaries

Excalidraw MCP communicates with AI agents over standard input/output (`stdio`) using the Model Context Protocol (MCP) JSON-RPC 2.0 specification.

- **Local Process Execution**: When running as an MCP stdio server, `exca-mcp` runs locally as a child process of your MCP client (Claude Desktop, Cursor, Zed, OpenCode, Codex, etc.).
- **Process Isolation**: The server operates with the privileges of the executing user account. It does not spawn background processes or listen on network sockets unless the optional live server is explicitly launched.

## Filesystem Write Confinement & Sandboxing

The server strictly restricts filesystem write access to prevent directory traversal or unauthorized file modification.

### 1. Scene Persistence (`save`)
- Saved `.excalidraw` scenes are written only to the directory specified by `EXCALIDRAW_SCENE_DIR` (defaults to `.excalidraw` in the current working directory).
- File names must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`. Path separators (`/`, `\`), null bytes, parent references (`..`), and symlinks are rejected.

### 2. Image Exports (`export_png`)
- PNG exports are restricted to an explicit whitelist of allowed directories:
  1. Configured export directory (`EXCALIDRAW_EXPORT_DIR`, defaults to `./exports`)
  2. Configured scene directory (`EXCALIDRAW_SCENE_DIR`)
  3. Current working directory (`Path.cwd()`)
  4. System temporary directory (`tempfile.gettempdir()`)
- Any export path outside these roots is rejected with a validation error.
- Image names are validated against `^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$`.

### 3. Agent Skills Installation (`exca-mcp install-skills`)
- Skill installation requires an explicit target directory (`--target <path>`).
- Writing to system root (`/`) is explicitly rejected.
- Directory traversal and escaping symlinks are rejected.
- Existing skill directories are never overwritten unless the `--force` flag is provided.

## Live Canvas Server Security

When the optional browser canvas server is started (`start_live_server`), additional network security controls are enforced:

### 1. Token Authentication (`EXCALIDRAW_LIVE_TOKEN`)
Set `EXCALIDRAW_LIVE_TOKEN` to require a shared secret for all live canvas operations:
- **Browser UI (`GET /`)**: The web UI automatically injects the secret into its WebSocket connection (`/ws?token=<token>`).
- **REST API (`POST /api/scene`)**: Mutating requests require the token via:
  - Header: `Authorization: Bearer <token>`
  - Header: `x-auth-token: <token>`
  - Query parameter: `?token=<token>`
  - Unauthenticated mutations return HTTP `401 Unauthorized`.
- **WebSocket Synchronization (`/ws`)**: WebSockets require the token via query parameter or header. Unauthorized attempts are closed with code `1008` (Policy Violation).

### 2. Cross-Site WebSocket Hijacking (CSWSH) Origin Protection
The live server validates incoming request origins against an allowlist:
- Permitted origins: `localhost`, `127.0.0.1`, and `https://excalidraw.com`.
- Unrecognized or cross-origin WebSocket connection requests are rejected with close code `1008`.

### 3. Remote Network Binding Guard (`EXCALIDRAW_ALLOW_REMOTE`)
- By default, the live server binds only to loopback interfaces (`127.0.0.1` or `localhost`).
- Binding to `0.0.0.0` or external network interfaces is blocked unless explicitly overridden by setting `EXCALIDRAW_ALLOW_REMOTE=true`. This prevents accidental exposure of the canvas to local networks.

## Reporting a Vulnerability

If you discover a security vulnerability in Excalidraw MCP, please report it via the [GitHub Security Advisory form](https://github.com/Dharshan2208/excalidraw-mcp/security/advisories/new).
