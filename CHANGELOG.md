# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
