# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-11-23

### Added
- **Streamable HTTP Transport**: Added `--transport streamable-http` with `--host`, `--port`, and `--path` options for remote and containerized deployments.
- **Obsidian Export**: Added native export to `.excalidraw.md` format (`scene_storage(format="obsidian")`) compatible with Obsidian Excalidraw plugin.
- **Claude Code CLI Skill Support**: Added `exca-mcp install-skills --claude` installing unified skill metadata into `~/.claude/skills/excalidraw/` with linked references.
- **Developer Experience Subcommands**:
  - `exca-mcp print-config [client]`: Prints copy-pasteable configuration for Claude Desktop, Cursor, Zed, Windsurf, OpenCode, and Antigravity.
  - `exca-mcp doctor`: Non-destructive sub-second diagnostic verification of Python runtime, TrueType fonts, storage directory, and skills.
- **Container Readiness Probe**: Added `/health` endpoint returning `{"status": "healthy"}` for container readiness probes.
- **MCP Registry Manifest**: Added `server.json` manifest conforming to `2025-12-11` schema and ownership marker to `README.md`.

### Security
- Added Origin and Content-Type validation to live canvas server `POST /api/scene` to protect against cross-origin canvas overwrites (CSRF).
- Escaped `%%` delimiters in Obsidian export serializer to prevent comment block breakout.
- Added symlink rejection to `export_obsidian` destination paths matching `export_png` and `export_svg`.
- Bumped Starlette dependency requirement to `>=0.40.0` to guard against multipart parsing DoS.

### Fixed
- Fixed Docker container build failure by bundling `.skills/` into the Docker build context.
- Fixed `EntrypointTests` failure on `python -m unittest discover` by filtering runner arguments in `server.py`.
- Mocked cloud sharing web calls during font integration tests to guarantee air-gapped test execution.
- Synchronized all 6 packaged agent skills and MCP task prompts to use canonical v0.3.0 tool signatures.
- Corrected safety annotations (`idempotentHint`, `destructiveHint`, `openWorldHint`) across tools.
- Handshake `serverInfo.version` now advertises package version rather than FastMCP library version.
- Silenced FastMCP stderr banner output on CLI `main()` invocations.

## [0.3.0] - 2026-11-19

### Changed
- **BREAKING (Tool Rationalization)**: Consolidated 48 legacy tools into 12 tools in the default `core` profile and 20 tools in the `full` profile.
  - Merged `add_rectangle`, `add_circle`, `add_diamond` into `create_shape`.
  - Merged `add_arrow` and `connect` into `create_connector` with obstacle-avoiding orthogonal routing.
  - Absorbed `move` and `resize` coordinates and dimensions into `update_element`.
  - Merged 8 scene inspection and query tools into unified `inspect_scene` (`summary`, `describe`, `elements`, `element`, `find`, `viewport`, `live_server`, `resource`).
  - Merged procedural diagram creators (`draw_mermaid`, `draw_architecture`, `draw_graph`) into `generate_diagram`.
  - Consolidated file persistence (`save`, `load`, `list_saved_scenes`, `export_scene`, `import_scene`) into `scene_storage`.
  - Consolidated element protection, grouping, and cloning (`set_element_locked`, `manage_groups`, `duplicate_elements`) into `manage_element_state`.
  - Merged live canvas server management (`start_live_server`, `stop_live_server`) into `live_server`.
- **Promoted `batch_mutate` to Core**: Multi-operation atomic diagram generation, updates, and styling are now available in the default `core` toolset with dynamic `$ref` client ID resolution.
- **Slim Response Defaults**: `describe_scene` and `auto_fix_layout` now default to `detailed=False`, reducing per-call response tokens by 72.4% and 94.5% respectively. Complete defect reports and element lists remain accessible via `detailed=True`.
- **Dynamic Version Detection**: Server reports package version dynamically via `importlib.metadata.version("exca-mcp")`.

### Added
- **Preview Optimization**: Added `max_dimension=1568` aspect-ratio downscaling (matching Claude's 1.6-megapixel vision threshold) and format selection (`format="png" | "jpeg"`) to `preview`.
- **MCP Resources**:
  - `excalidraw://fonts`: Static JSON resource for system fonts, Excalifont paths, and default font categories.
  - `excalidraw://guide/{topic}`: Parameterized markdown resource for design rules (`layout`, `colors`, `typography`, `grouping`, `arrows`, `spacing`).
- **Server Instructions**: Added concise system prompt instructions (35 words, 56 tokens) to FastMCP initialization for agent guidance.
- **Migration Guide**: Added [docs/migration_v030.md](docs/migration_v030.md) detailing migration mapping for all 48 baseline tools.
- **Capability Coverage Tests**: Added `tests/test_capability_coverage.py` asserting all 48 baseline features remain functional.
- **Docs Sync Verification**: Added `tests/test_docs_sync.py` asserting registered tool sets match documentation.

### Removed
- Removed legacy wrapper tools: `lock_elements`, `unlock_elements`, `group_elements`, `ungroup_elements`, and `focus_elements`.
- Removed standalone `add_code_block` tool (syntax-highlighted code blocks are authored directly via `batch_mutate`).
- Removed `list_fonts` tool in favor of the `excalidraw://fonts` MCP resource.

## [0.2.1] - 2026-11-07

### Added
- Agent Skills distribution system with CLI installer (`exca-mcp install-skills`).
- MCP resources and prompts for agent skill discovery (`excalidraw://skills`, `excalidraw://skills/{name}`).
- Dedicated security guide (`docs/security.md`) and security advisory policy (`SECURITY.md`).

## [0.2.0] - 2026-10-29

### Changed
- **BREAKING CHANGE (Default Toolset)**: The server now defaults to the streamlined `core` toolset (27 tools) instead of the full 48-tool set. This reduces the prompt schema payload by approximately 45.2% (~6,560 tokens per turn).
- Set `EXCALIDRAW_TOOLSET=full` to restore all 48 tools.
- Consolidated element locking into `set_element_locked` with backward-compatibility wrappers (`lock_elements`, `unlock_elements`).
- Consolidated grouping into `manage_groups` with backward-compatibility wrappers (`group_elements`, `ungroup_elements`).
- Unified camera viewport control via `set_viewport` with element focusing.

### Added
- Automated layout repair engine (`auto_fix_layout`) with 5 topological repair phases and transactional rollback guarantee.
- Mermaid syntax rendering (`draw_mermaid`) supporting flowchart and graph diagrams.
- Syntax-highlighted code block primitive (`add_code_block`).
- Live canvas server authentication (`EXCALIDRAW_LIVE_TOKEN`), CSWSH origin validation, and remote interface binding guard (`EXCALIDRAW_ALLOW_REMOTE`).
- Zero-token capability discovery via `excalidraw://capabilities` resource.

## [0.1.0] - 2026-09-20

### Added
- Initial release of Excalidraw MCP Server (`exca-mcp`).
- Primitive shapes (`add_rectangle`, `add_circle`, `add_diamond`, `add_arrow`, `add_text`, `add_frame`).
- Coordinate connections (`connect`) and element mutations (`move`, `resize`, `update_element`, `delete`).
- Scene inspection, local persistence, and PNG image export.
