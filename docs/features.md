# Key Features & Capabilities

This document outlines the capabilities provided by the Excalidraw MCP Server (`exca-mcp`).

## 1. High-Level Diagram Generation
- **Mermaid Support (`draw_mermaid`)**: Convert standard Mermaid `flowchart` and `graph` syntax into native, editable Excalidraw elements.
- **Architecture Shorthand (`draw_architecture`)**: Rapidly sketch systems using comma/newline component descriptions (e.g. `box: Frontend, db: Postgres`).
- **Layered Graph Generator (`draw_graph`)**: Programmatic hierarchical graph layout with topological ranking, clustered frame grouping, and edge routing.
- **Design Guidelines (`read_diagram_guide`)**: Built-in design guidance for agents covering palettes, dimensions, and visual hierarchy.

## 2. Primitive Elements & Composition
- **Geometric Primitives**: Rectangles (`add_rectangle`), circles/ellipses (`add_circle`), diamonds (`add_diamond`), and coordinate arrows (`add_arrow`).
- **Smart Connectors (`connect`)**: Bind shapes with arrows that automatically track element moves and resizes.
- **Code Blocks (`add_code_block`)**: Render syntax-highlighted code blocks with window chrome and monospace styling.
- **Frames (`add_frame`)**: Container elements that group and move child elements hierarchically.
- **Atomic Operations (`batch_mutate`)**: Execute multiple creations, movements, and connections in a single revision step with rollback on failure.

## 3. Automated Layout Repair (`auto_fix_layout`)
- Analyzes scene geometry to detect overlaps, text clipping, and crowded nodes.
- Repairs layout defects across 5 topological phases.
- Includes `dry_run=True` simulation and automatic rollback on regression. See [docs/auto-fix-layout.md](auto-fix-layout.md).

## 4. Inspection, Persistence & Export
- **Element Querying**: Inspect active scenes using `get_scene`, `get_element`, or `find_elements`.
- **Textual Scene Summaries**: High-level semantic summaries via `describe_scene` and `get_scene_summary`.
- **Direct Image Previews**: Generate inline PNG previews directly into agent chat via `preview`.
- **File Export**: Save `.excalidraw` scenes (`save`) and high-resolution PNG images (`export_png`).
- **Web Sharing (`export_to_excalidraw_url`)**: Export scenes directly to shareable, client-side encrypted `excalidraw.com` links.

## 5. Live Canvas Synchronization (`start_live_server`)
- Background web server with live bidirectional WebSocket synchronization.
- Watch AI agents create and modify diagrams in real time inside a local web browser.
- Secured via token authentication, origin validation, and localhost interface guards. See [docs/security.md](security.md).

## 6. First-Class Agent Skills
- Distribution of 6 specialized agent skills bundled in PyPI packages and accessible via MCP resources, prompts, and CLI (`exca-mcp install-skills`). See [docs/skills.md](skills.md).
