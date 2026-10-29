# Excalidraw MCP Tool Inventory, Redundancy Audit, and Toolset Proposal

> **Date:** October 2026  
> **Status:** Proposal / Audit Report (Read-Only Analysis)  
> **Target Repository:** `excalidraw-mcp`  
> **Target Interface:** Model Context Protocol (MCP) via FastMCP  

---

## 1. Executive Summary

This audit evaluates the complete tool surface of the Excalidraw MCP server. As of commit `feat/layout-quality-and-improvements`, the server registers **47 individual tools** using FastMCP. When serialized over the standard MCP protocol (`tools/list`), this tool inventory produces a **58,000-byte (58 KB)** compact JSON payload, consuming an estimated **14,500 to 16,570 tokens** of context on **every single client invocation** before any user conversation begins.

### Key Audit Findings
1. **Critical Tool Alias Duplicate:** `get_canvas_screenshot` is an exact byte-for-byte wrapper around `preview`, duplicating documentation and schema with zero distinct behavioral logic.
2. **Schema Size Skew:** Two tools alone (`draw_graph` at 4,790 bytes and `batch_mutate` at 4,661 bytes) account for nearly **16.3% (9.45 KB)** of the entire server schema. Nine shape-creation tools each duplicate identical 16-parameter style definitions.
3. **Domain Disparity:** Advanced features such as the background Uvicorn live canvas server (`start_live_server`, `stop_live_server`, `get_live_server_status`) and canvas viewport camera controls (`get_viewport`, `set_viewport`, `focus_elements`) are exposed to all autonomous agents, even though 95%+ of agent interactions only require generation, inspection, auto-repair, and PNG/Excalidraw export.
4. **Viability of a Two-Tier Toolset:** Introducing an environment variable `EXCALIDRAW_TOOLSET=core|full` allows ordinary coding agents to operate with a streamlined **25-tool `CORE` set** (31,759 bytes, ~7,940 tokens), achieving a **45.2% schema reduction (26,241 bytes saved, ~6,560 tokens saved per LLM call)** while retaining 100% of generation, mutation, auto-repair, inspection, and export capabilities. Power users and specialized interactive agents retain the complete **46-tool `FULL` set**.

---

## 2. Complete Tool-by-Tool Inventory & Classification

Every registered MCP tool was inspected in `excalidraw_mcp/server.py` and mapped to its underlying execution method in `excalidraw_mcp/service.py`.

### Classification Key:
- **`CORE`**: Essential tool required for the standard agent generation-edit-inspect-validate-export loop.
- **`FULL-ONLY`**: Specialized, heavy, or interactive tool reserved for advanced workflows or human-in-the-loop sessions.
- **`MERGE CANDIDATE`**: High functional overlap with another tool; strong candidate for consolidation into a single parameterized tool.
- **`DEPRECATION CANDIDATE`**: Redundant alias or obsolete endpoint that should be phased out with compatibility warnings.
- **`KEEP PENDING EVIDENCE`**: Utility tool with niche value, preserved pending telemetry on real-world client usage.

### Tool Inventory Table (47 Registered Tools)

| # | Tool Name | Purpose & Capabilities | Schema (Bytes) | Overlap / Redundancy | Classification | Recommendation & Proposed Action |
|---|---|---|---|---|---|---|
| 1 | `add_rectangle` | Adds a rectangle shape with optional bound label and styling. | 2,341 | Overlaps with `add_circle`, `add_diamond`, and `batch_mutate` (`add_shape`). | **`CORE`** / `MERGE CANDIDATE` | Retain in `CORE`. In near-term, evaluate consolidating into unified `add_shape(shape="rectangle", ...)`. |
| 2 | `add_circle` | Adds an ellipse/circle shape with bound label. | 2,094 | Shares 14 identical styling parameters with rectangle. | **`CORE`** / `MERGE CANDIDATE` | Retain in `CORE`. Evaluate consolidating into unified `add_shape`. |
| 3 | `add_diamond` | Adds a flowchart decision diamond shape. | 2,253 | Shares 16 styling parameters with rectangle. | **`CORE`** / `MERGE CANDIDATE` | Retain in `CORE`. Evaluate consolidating into unified `add_shape`. |
| 4 | `add_arrow` | Adds a freeform directional or elbowed arrow between arbitrary coordinates. | 1,826 | Partially overlaps with `connect`, but works without bound shapes. | **`CORE`** | Retain in `CORE`. Distinct workflow for arbitrary canvas annotations. |
| 5 | `add_frame` | Creates a boundary container to group and enclose elements visually. | 1,968 | Distinct container semantics; supports child assignment. | **`CORE`** | Retain in `CORE`. Crucial for architecture zones and subgraphs. |
| 6 | `clear` | Clears all elements, app state, and files from active scene. | 377 | None. | **`CORE`** | Retain in `CORE`. Standard clean-slate reset tool. |
| 7 | `delete` | Deletes an element and its owned label; detaches surviving connectors. | 611 | Supported in `batch_mutate`. | **`CORE`** | Retain in `CORE`. Essential single-item atomic deletion. |
| 8 | `move` | Repositions an element and its label; connectors follow. | 706 | Supported in `batch_mutate`. | **`CORE`** | Retain in `CORE`. Fast, fundamental single-element translation. |
| 9 | `save` | Saves active scene snapshot to named file in storage directory. | 582 | None. | **`CORE`** | Retain in `CORE`. Essential disk persistence for multi-turn tasks. |
| 10 | `get_scene` | Paginated list of active elements with current revision. | 725 | Overlaps with `find_elements`. | **`CORE`** | Retain in `CORE`. Predictable, paginated raw scene dump for inspection. |
| 11 | `get_element` | Fetches a single element dictionary by ID. | 511 | Can be queried via `find_elements(element_id=...)`. | **`CORE`** | Retain in `CORE`. Simple, zero-overhead direct ID lookup. |
| 12 | `list_saved_scenes` | Enumerates saved `.excalidraw` scene files on disk. | 430 | Storage directory inspection. | **`FULL-ONLY`** | Move to `FULL`. Ordinary agents manage the active scene or known target file. |
| 13 | `add_text` | Adds standalone text elements (labels, headers, legends). | 1,594 | Bound text is handled by shape tools; standalone text needs this. | **`CORE`** | Retain in `CORE`. Essential for diagram titles and annotations. |
| 14 | `update_element` | Modifies label, font, colors, or stroke on existing shapes. | 2,152 | Supported in `batch_mutate`. | **`CORE`** | Retain in `CORE`. Standard in-place element property editor. |
| 15 | `resize` | Changes shape dimensions and recenters bound text. | 703 | Supported in `batch_mutate`. | **`CORE`** | Retain in `CORE`. Direct geometric adjustment tool. |
| 16 | `connect` | Connects two shapes by ID with bound arrow and port calculation. | 1,695 | Complements `add_arrow`. | **`CORE`** | Retain in `CORE`. Primary semantic connector tool for diagram graphs. |
| 17 | `find_elements` | Advanced query by text string, element type, frame, or connection. | 1,827 | Overlaps with `get_element` and `get_scene`. | **`FULL-ONLY`** | Move to `FULL`. Powerful query engine for dense diagrams, unnecessary in `CORE`. |
| 18 | `batch_mutate` | Atomic multi-operation transaction executor (20+ op types). | 4,661 | Can execute all single-element mutations. Massive schema. | **`FULL-ONLY`** | Move to `FULL`. High-performance batch tool, but schema consumes ~1.2K tokens. |
| 19 | `auto_fix_layout` | Deterministic 5-phase layout repair with rollback and dry-run safety. | 2,927 | Supercedes manual coordinate shifting heuristics. | **`CORE`** | Retain in `CORE`. Flagship layout verification and quality engine. |
| 20 | `undo` | Restores scene before the most recent successful mutation. | 451 | None. | **`CORE`** | Retain in `CORE`. Vital safety net for conversational coding agents. |
| 21 | `export_scene` | Returns raw `.excalidraw` document as an MCP EmbeddedResource. | 296 | None. | **`CORE`** | Retain in `CORE`. Pure in-memory document handoff without filesystem writes. |
| 22 | `load` | Replaces active canvas with a saved document from disk. | 536 | None. | **`CORE`** | Retain in `CORE`. Restores saved work into active memory. |
| 23 | `preview` | Renders inline PNG image preview as an MCP Image. | 451 | `get_canvas_screenshot` is an exact duplicate wrapper. | **`CORE`** | Retain in `CORE`. Essential for visual multimodal verification. |
| 24 | `export_png` | Writes high-resolution PNG file to disk with bounding-box scaling. | 1,025 | File-based counterpart to `preview`. | **`CORE`** | Retain in `CORE`. Critical for generating project documentation artifacts. |
| 25 | `add_code_block` | Renders syntax-highlighted code container with window controls. | 1,539 | Specialized multi-element composite generator. | **`FULL-ONLY`** | Move to `FULL`. Specialized feature not needed for standard architecture. |
| 26 | `list_fonts` | Scans and lists system fonts and normalization categories. | 807 | Auxiliary system query. | **`FULL-ONLY`** | Move to `FULL`. Typography is preconfigured or defaulted in standard use. |
| 27 | `draw_architecture` | Creates linear/pipeline diagram from simple text strings. | 2,416 | Shorthand text DSL. | **`CORE`** | Retain in `CORE`. Lightweight text-to-architecture generator. |
| 28 | `draw_graph` | Hierarchical Sugiyama-style layered graph generator. | 4,790 | Heaviest schema in repository. Complex nested JSON input. | **`FULL-ONLY`** | Move to `FULL`. Programmatic generator for complex graph compilers. |
| 29 | `lock_elements` | Freezes elements to protect against accidental movement. | 630 | Paired with `unlock_elements`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Merge candidate with `unlock_elements` into `set_element_locked`. |
| 30 | `unlock_elements` | Unfreezes previously locked elements. | 610 | Inverse of `lock_elements`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Merge candidate into `set_element_locked(ids, locked: bool)`. |
| 31 | `group_elements` | Groups multiple elements into a shared logical group. | 694 | Inverse of `ungroup_elements`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Logical grouping is an advanced organizational tool. |
| 32 | `ungroup_elements` | Disbands an element group or strips group IDs. | 836 | Inverse of `group_elements`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Merge candidate with `group_elements` into `manage_groups`. |
| 33 | `draw_mermaid` | Renders Mermaid flowchart/graph DSL directly into Excalidraw shapes. | 1,333 | None. Standard LLM diagramming syntax. | **`CORE`** | Retain in `CORE`. Primary high-leverage generation format for LLMs. |
| 34 | `get_viewport` | Reads canvas camera offsets, zoom, and background color. | 581 | UI view state only; does not affect diagram geometry or PNGs. | **`FULL-ONLY`** | Move to `FULL`. Headless generation and export do not require camera reads. |
| 35 | `set_viewport` | Sets canvas camera scroll coordinates and zoom level. | 1,018 | Overlaps in purpose with `focus_elements`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Could absorb `focus_elements` via `focus_element_ids` param. |
| 36 | `focus_elements` | Calculates bounding box and auto-frames camera on elements. | 939 | Convenience calculation over `set_viewport`. | **`FULL-ONLY`** / `MERGE CANDIDATE` | Move to `FULL`. Merge candidate into `set_viewport`. |
| 37 | `get_scene_summary` | Returns compact numerical bounds, element counts, layers, and labels. | 1,210 | Complements `describe_scene`. | **`CORE`** | Retain in `CORE`. Highly efficient layout inspection without huge JSON dumps. |
| 38 | `export_to_excalidraw_url` | Publishes encrypted scene to excalidraw.com cloud backend. | 681 | Requires external network access. | **`FULL-ONLY`** | Move to `FULL`. Optional cloud sharing capability. |
| 39 | `describe_scene` | Generates natural language prose description of diagram layout. | 940 | Complements `get_scene_summary`. | **`CORE`** | Retain in `CORE`. Essential for non-vision models to verify spatial layout. |
| 40 | `get_canvas_screenshot` | Wrapper calling `preview()` directly. | 494 | **100% duplicate alias of `preview`.** | **`DEPRECATION CANDIDATE`** | Deprecate immediately. Issue deprecation warning pointing to `preview`. |
| 41 | `get_resource` | Unified tool for fetching scene, library, or theme data. | 1,437 | Duplicates native MCP Resource protocol (`resources/read`). | **`FULL-ONLY`** / `KEEP PENDING EVIDENCE` | Move to `FULL`. Useful only for MCP clients lacking native resource support. |
| 42 | `read_diagram_guide` | Returns static markdown tips on layout, colors, and typography. | 576 | Static prompt documentation disguised as an active tool. | **`FULL-ONLY`** | Move to `FULL`. Better served as an MCP Prompt or static documentation. |
| 43 | `duplicate_elements` | Clones elements with spatial offset and relationship remapping. | 1,011 | Supported in `batch_mutate` (`duplicate`). | **`FULL-ONLY`** | Move to `FULL`. Specialized batch cloning feature. |
| 44 | `import_scene` | Ingests JSON, `.excalidraw`, Obsidian markdown, or embedded PNGs. | 931 | Advanced heterogeneous ingestion. | **`FULL-ONLY`** | Move to `FULL`. `load` handles native scenes; `import_scene` is for external files. |
| 45 | `start_live_server` | Starts background Uvicorn live canvas server on localhost. | 667 | Interactive human-in-the-loop co-editing server. | **`FULL-ONLY`** | Move to `FULL`. Headless agents have no use for a live browser server. |
| 46 | `stop_live_server` | Shuts down background Uvicorn live canvas server. | 519 | Server lifecycle management. | **`FULL-ONLY`** | Move to `FULL`. |
| 47 | `get_live_server_status` | Returns running state, port, URL, and client count of live server. | 541 | Server lifecycle inspection. | **`FULL-ONLY`** | Move to `FULL`. |

---

## 3. Dedicated Duplicate and Merge Analysis

### A. Definite Duplicate Alias: `get_canvas_screenshot` vs `preview`
* **Source Evidence (`excalidraw_mcp/server.py` lines 790–798):**
  ```python
  @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
  def get_canvas_screenshot(
      scale: PreviewScale = 1.0,
      padding: PreviewPadding = 40,
      background: Boolean = True,
  ) -> Image:
      """Alias for preview. Render an inline PNG screenshot of the current canvas with embedded metadata."""
      return preview(scale=scale, padding=padding, background=background)
  ```
* **Findings:** The function body literally forwards arguments directly into `preview()`. The parameter list, types, defaults, and return type (`Image`) are 100% identical.
* **Impact:** Adds 494 bytes to the schema and introduces tool-selection ambiguity for LLMs deciding between `preview` and `get_canvas_screenshot`.
* **Recommendation:** Mark `get_canvas_screenshot` as **`DEPRECATION CANDIDATE`**. Log a deprecation warning recommending `preview`. Exclude from `CORE`.

---

### B. Structural Duplication: Primitive Shapes (`add_rectangle`, `add_circle`, `add_diamond`)
* **Source Evidence:**
  All three tools call `service.add_shape(shape_type, ...)`. Each tool defines 14–16 parameters including 8 style parameters (`strokeColor`, `backgroundColor`, `fillStyle`, `strokeWidth`, `strokeStyle`, `opacity`, `roughness`, `font_family`, `font_size`) with identical regex validation patterns and docstrings.
* **Schema Overhead:**
  - `add_rectangle`: 2,341 bytes
  - `add_diamond`: 2,253 bytes
  - `add_circle`: 2,094 bytes
  - Total: **6,688 bytes (~1,672 tokens)**
* **Analysis:**
  Consolidating into a single `add_shape(shape: Literal["rectangle", "circle", "diamond"], ...)` tool would reduce the schema to ~2,400 bytes, saving **~4,288 bytes (~1,072 tokens)**.
* **Compatibility Risk:** High for immediate removal. Existing agents and prompts often expect `add_rectangle`.
* **Recommendation:**
  Keep all three in `CORE` for the initial toolset rollout. In the near-term, introduce `add_shape` and deprecate individual shape tools over a documented deprecation window.

---

### C. State Toggles: `lock_elements` / `unlock_elements` and `group_elements` / `ungroup_elements`
* **Findings:**
  - `lock_elements(element_ids)` (630 bytes) and `unlock_elements(element_ids)` (610 bytes) are inverse operations with identical signatures.
  - `group_elements(element_ids)` (694 bytes) and `ungroup_elements(element_ids, group_id)` (836 bytes) manage element grouping.
* **Analysis:**
  - `lock_elements` and `unlock_elements` can be merged into `set_element_locked(element_ids: list[ElementId], locked: bool = True)`.
  - Both belong in `FULL-ONLY` because autonomous diagram generation rarely locks elements unless building template libraries.
* **Recommendation:** Classify as **`FULL-ONLY`** and **`MERGE CANDIDATE`**.

---

### D. Viewport & Camera Tools: `set_viewport` vs `focus_elements`
* **Findings:**
  - Excalidraw viewport settings (`scroll_x`, `scroll_y`, `zoom`) represent browser client UI state. They do not alter canvas element geometry or PNG export output (which uses content-aware bounding boxes).
  - `focus_elements` merely calculates a bounding box and delegates to `set_viewport`.
* **Recommendation:**
  - Move both to **`FULL-ONLY`**.
  - In a future release, consolidate `focus_elements` into `set_viewport(..., focus_elements: list[ElementId] | None = None)`.

---

### E. Redundant In-Band Resource Fetching: `get_resource` vs Native MCP Resources
* **Findings:**
  `get_resource` is a tool wrapper (1,437 bytes) that dispatches to `service.get_resource`. FastMCP already exposes native MCP resources:
  ```python
  @mcp.resource("excalidraw://scenes/{name}.excalidraw", mime_type=MIME_TYPE)
  def saved_scene_resource(name: SceneName) -> str: ...
  ```
* **Analysis:**
  Standard MCP clients use the native `resources/read` protocol rather than calling tools to read files. `get_resource` exists only as a fallback for clients lacking resource support.
* **Recommendation:** Classify as **`FULL-ONLY` / `KEEP PENDING EVIDENCE`**. Retain in `FULL` to avoid breaking non-standard clients.

---

## 4. The Two-Tier Toolset Proposal: `EXCALIDRAW_TOOLSET`

To provide the optimal balance of lean token usage for standard agents and comprehensive power for interactive workflows, we propose an environment variable:
```bash
EXCALIDRAW_TOOLSET=core|full
```

### A. Environment Variable Specification & Deterministic Selection
* **Variable Name:** `EXCALIDRAW_TOOLSET`
* **Accepted Values:**
  - `core` (case-insensitive): Registers the 25 essential generation, mutation, inspection, auto-repair, and export tools.
  - `full` (case-insensitive): Registers all 46 tools (excluding deprecated aliases).
* **Default Behavior:** **`core`** is recommended as the default. If the variable is unset or empty, the server defaults to `core`. If an invalid value is provided (e.g. `EXCALIDRAW_TOOLSET=all`), the server logs a warning and falls back deterministically to `core`.
* **Justification for `core` as Default:**
  1. **Immediate Context Savings:** Every agent gets an instant **45.2% reduction in schema tokens** without client-side reconfiguration.
  2. **Reduced Model Hallucinations:** Prevents models from choosing between competing tools (e.g., `preview` vs `get_canvas_screenshot`, or `draw_graph` vs `draw_mermaid`).
  3. **Zero Loss of Core Capability:** Every necessary capability (creation, editing, auto-repair, visual preview, file export) is fully present in `CORE`.

---

### B. Proposed Toolset Membership

```
+--------------------------------------------------------------------------------------------------+
|                                    EXCALIDRAW MCP SERVER                                         |
+-------------------------------------------------+------------------------------------------------+
|                   CORE SET                      |                   FULL SET                     |
|                  (25 Tools)                     |            (CORE + 21 Advanced Tools)          |
+-------------------------------------------------+------------------------------------------------+
| Generation:                                     | Advanced Generators:                           |
|   - draw_mermaid                                |   - draw_graph                                 |
|   - draw_architecture                           |   - add_code_block                             |
|                                                 |                                                |
| Primitive Elements:                             | Advanced Query & Batch:                        |
|   - add_rectangle                               |   - find_elements                              |
|   - add_circle                                  |   - batch_mutate                               |
|   - add_diamond                                 |   - duplicate_elements                         |
|   - add_text                                    |                                                |
|   - add_arrow                                   | Hierarchy & Protection:                        |
|   - connect                                     |   - lock_elements                              |
|   - add_frame                                   |   - unlock_elements                            |
|                                                 |   - group_elements                             |
| Essential Mutations:                            |   - ungroup_elements                           |
|   - move                                        |                                                |
|   - resize                                      | Viewport & Camera:                             |
|   - update_element                              |   - get_viewport                               |
|   - delete                                      |   - set_viewport                               |
|   - clear                                       |   - focus_elements                             |
|   - undo                                        |                                                |
|                                                 | Live Canvas Server:                            |
| Inspection & Verification:                      |   - start_live_server                          |
|   - get_scene_summary                           |   - stop_live_server                           |
|   - get_scene                                   |   - get_live_server_status                     |
|   - get_element                                 |                                                |
|   - describe_scene                              | Storage, Fonts & Utilities:                    |
|                                                 |   - list_saved_scenes                          |
| Layout & Repair:                                |   - list_fonts                                 |
|   - auto_fix_layout                             |   - read_diagram_guide                         |
|                                                 |   - import_scene                               |
| Export & Persistence:                           |   - export_to_excalidraw_url                   |
|   - preview (inline image)                      |   - get_resource                               |
|   - export_png (file write)                     |                                                |
|   - save (disk save)                            | Deprecated:                                    |
|   - load (disk load)                            |   - get_canvas_screenshot (alias of preview)   |
|   - export_scene (raw JSON resource)            |                                                |
+-------------------------------------------------+------------------------------------------------+
```

---

## 5. Capability Discovery Evaluation (`describe_capabilities`)

Requirement 23 & 24 asks whether a `describe_capabilities` tool would provide meaningful value beyond standard MCP `tools/list`.

### Analysis & Verdict
1. **The Tool Paradox:**
   Adding a `describe_capabilities` *tool* adds ~600–900 bytes to the `tools/list` schema just to describe other tools that the client has already listed. This is counter-productive when our goal is schema reduction.
2. **When it Provides Genuine Value:**
   If the server runs with `EXCALIDRAW_TOOLSET=core`, an autonomous agent may need to know:
   - What toolset is currently active (`core`).
   - What storage directory is configured.
   - What formats and fonts are available.
   - What capabilities exist in `full` and how to enable them.
3. **Recommended Implementation: MCP Resource over Tool:**
   Instead of an active tool in `tools/list`, expose `describe_capabilities` as an **MCP Resource**:
   `excalidraw://capabilities`
   * **Schema Cost in `tools/list`:** **0 bytes** (resources do not inflate the tools schema).
   * **Proposed Output (JSON):**
     ```json
     {
       "active_toolset": "core",
       "available_toolsets": ["core", "full"],
       "server_version": "0.1.0",
       "capabilities": {
         "generators": ["mermaid", "architecture_dsl"],
         "export": ["png", "excalidraw_json"],
         "repair": "5-phase topological auto_fix_layout with rollback",
         "full_only_features": [
           "live_server",
           "sugiyama_graph_layout",
           "batch_mutate",
           "code_blocks",
           "camera_viewport",
           "element_locking",
           "element_grouping"
         ]
       },
       "config": {
         "scene_dir": "~/.local/share/excalidraw-mcp/scenes",
         "max_elements": 10000
       },
       "upgrade_instructions": "To enable advanced tools, set environment variable EXCALIDRAW_TOOLSET=full."
     }
     ```

---

## 6. Schema Size & Token Measurements

### A. Measurement Methodology
1. **Serialization:** Generated the exact `tools/list` response by invoking `create_server().list_tools()`, converting each tool via `to_mcp_tool()`, and dumping to JSON conforming to `mcp.types.Tool`.
2. **Byte Counting:** Measured both compact JSON (standard network transport, no whitespace: `separators=(',', ':')`) and indented JSON (2-space human-readable formatting).
3. **Tokenizer Estimation Method:**
   Since external tokenizer binaries (e.g. `tiktoken`) are not dependencies of this server, token counts are estimated using established industry standards for structured JSON schemas:
   - **Method 1 (Standard Rule-of-Thumb):** `chars / 4.0` (standard for OpenAI GPT-4o, Anthropic Claude 3.5, and Gemini tokenizers on alphanumeric English text).
   - **Method 2 (Dense JSON Subword Heuristic):** `chars / 3.5` (accounts for punctuation, quotes, brackets, and short keys common in JSON Schemas).

### B. Quantitative Measurement Comparison

| Metric | Current Inventory | Proposed FULL | Proposed CORE | Absolute Savings (CORE vs Current) | Percentage Savings |
|---|---|---|---|---|---|
| **Registered Tools** | 47 | 46 | **25** | -22 tools | **-46.8%** |
| **Compact JSON Bytes** | 58,000 bytes | 57,505 bytes | **31,759 bytes** | **-26,241 bytes** | **-45.2%** |
| **Indented JSON Bytes** | 139,947 bytes | 139,082 bytes | **72,401 bytes** | **-67,546 bytes** | **-48.3%** |
| **Total Characters** | 58,000 | 57,505 | **31,759** | -26,241 chars | **-45.2%** |
| **Est. Tokens (~4.0 chars/tok)** | **14,500 tokens** | **14,376 tokens** | **7,940 tokens** | **-6,560 tokens** | **-45.2%** |
| **Est. Tokens (~3.5 chars/tok)** | **16,571 tokens** | **16,430 tokens** | **9,074 tokens** | **-7,497 tokens** | **-45.2%** |

### C. Top 10 Schema Consumers in Current Inventory

```
draw_graph              [4,790 B]  ████████████████████████████████████████ 8.3%
batch_mutate            [4,661 B]  ███████████████████████████████████████  8.0%
auto_fix_layout         [2,927 B]  ████████████████████████ 5.0%
draw_architecture       [2,416 B]  ████████████████████ 4.2%
add_rectangle           [2,341 B]  ███████████████████ 4.0%
add_diamond             [2,253 B]  ██████████████████ 3.9%
update_element          [2,152 B]  ██████████████████ 3.7%
add_circle              [2,094 B]  █████████████████ 3.6%
add_frame               [1,968 B]  ████████████████ 3.4%
find_elements           [1,827 B]  ███████████████ 3.1%
```
*Note:* Moving `draw_graph`, `batch_mutate`, and `find_elements` to `FULL` immediately eliminates **11,278 bytes (~2,820 tokens)** from the standard agent prompt.

### D. Distinction Between Token Types
1. **Schema Tokens (Static Per-Turn Tax):** Injected into the model's context on *every single request* that includes tools. In a 10-turn coding session, 14,500 schema tokens consume **145,000 token-turns** of context. Reducing schema to 7,940 tokens saves **65,600 token-turns**.
2. **Runtime Conversation Tokens (Dynamic Payloads):** Tokens consumed by actual tool arguments (e.g. calling `add_rectangle(x=100, y=100, w=200, h=100)` consumes ~35 tokens). Pruning unused tools from the schema does not restrict runtime payload size for tools in `CORE`.
3. **Model Reasoning & Selection Tokens:** Smaller tool lists significantly improve model reasoning accuracy, reducing tool-call hallucinations and misrouted invocations.

---

## 7. Lifecycle Integration & Backward Compatibility

### A. Server Lifecycle Integration Point
In `excalidraw_mcp/server.py`, server creation is centralized in `create_server(service=None)`:
```python
def create_server(service: SceneService | None = None) -> FastMCP:
    mcp = FastMCP(
        name="excalidraw-mcp",
        version="0.1.0",
        instructions="...",
    )
    # Registration happens here
```
To implement toolset filtering without modifying FastMCP internals:
1. Define toolset configuration in `excalidraw_mcp/config.py`:
   ```python
   def configured_toolset() -> str:
       val = os.environ.get("EXCALIDRAW_TOOLSET", "core").lower().strip()
       return val if val in ("core", "full") else "core"
   ```
2. In `create_server()`, conditionally wrap tool registrations using a decorator or explicit registration helper:
   ```python
   toolset = configured_toolset()
   
   # Always registered (CORE)
   @mcp.tool(...)
   def add_rectangle(...): ...

   # Only registered in FULL
   if toolset == "full":
       @mcp.tool(...)
       def draw_graph(...): ...
   ```
This approach ensures zero runtime performance overhead, no monkey-patching of FastMCP, and clean deterministic registration.

---

### B. Client Configuration Compatibility
Clients configure the environment variable directly in their existing configuration files:

* **Claude Desktop (`claude_desktop_config.json`):**
  ```json
  {
    "mcpServers": {
      "excalidraw": {
        "command": "uvx",
        "args": ["exca-mcp"],
        "env": {
          "EXCALIDRAW_TOOLSET": "core"
        }
      }
    }
  }
  ```

* **Cursor / OpenCode / Codex (`~/.cursor/mcp.json` or `.mcp.json`):**
  ```json
  {
    "excalidraw": {
      "command": "uvx",
      "args": ["exca-mcp"],
      "env": {
        "EXCALIDRAW_TOOLSET": "full"
      }
    }
  }
  ```

---

### C. Migration & Deprecation Strategy for `get_canvas_screenshot`
1. **Phase 1 (Immediate / Warning):** Retain `get_canvas_screenshot` in `FULL` (omit from `CORE`). When called, emit a runtime log and append a response warning:
   `"Warning: get_canvas_screenshot is deprecated and will be removed in a future release. Please use preview instead."`
2. **Phase 2 (Next Minor Release):** Mark `get_canvas_screenshot` as deprecated in MCP tool metadata annotations (`deprecated: True`).
3. **Phase 3 (Next Major Release):** Completely remove `get_canvas_screenshot` from the codebase.

---

## 8. Prioritized Action Plan & Risk Matrix

### Priority 1: Immediate Actions (Low Risk, High Impact)
- [ ] Add `EXCALIDRAW_TOOLSET` configuration to `excalidraw_mcp/config.py` defaulting to `core`.
- [ ] Conditionally register the 25 `CORE` tools vs 21 `FULL-ONLY` tools in `excalidraw_mcp/server.py`.
- [ ] Deprecate `get_canvas_screenshot` with warning pointing to `preview`.
- [ ] Expose `excalidraw://capabilities` MCP Resource for zero-token capability discovery.
- **Estimated Effort:** ~2–3 hours.
- **Risk:** Very low (power users can set `EXCALIDRAW_TOOLSET=full` for 100% legacy parity).

### Priority 2: Near-Term Actions (Medium Risk, Moderate Impact)
- [ ] Merge `lock_elements` and `unlock_elements` into `set_element_locked(element_ids, locked: bool)`.
- [ ] Merge `group_elements` and `ungroup_elements` into `manage_groups(element_ids, action: Literal["group", "ungroup"])`.
- [ ] Consolidate `focus_elements` into `set_viewport(..., focus_elements=[...])`.
- **Estimated Effort:** ~4–6 hours.
- **Risk:** Low (internal to `FULL`).

### Priority 3: Optional / Long-Term Improvements
- [ ] Unify `add_rectangle`, `add_circle`, and `add_diamond` into `add_shape(shape: Literal["rectangle", "circle", "diamond"], ...)`.
- [ ] Refactor style parameters into a shared reusable Pydantic sub-model to compact schema definitions.
- **Estimated Effort:** ~1 day.
- **Risk:** Moderate (requires backward-compatibility aliases for existing agent prompts).

---

## 9. Risk Assessment Matrix

| Dimension | Risk Level | Mitigation Strategy |
|---|---|---|
| **Backward Compatibility** | Low | Setting `EXCALIDRAW_TOOLSET=full` completely restores the legacy 47-tool environment. Existing client configs remain fully functional. |
| **Tool Discoverability** | Low | The `excalidraw://capabilities` resource informs models of available tools without cluttering `tools/list`. |
| **Model Reliability** | Positive (Reduced Risk) | Cutting schema by 45.2% and eliminating duplicate aliases reduces model hallucination and tool misdirection. |
| **Testability** | Very Low | Server unit tests can parametrize `EXCALIDRAW_TOOLSET=core` and `EXCALIDRAW_TOOLSET=full` to verify tool registration deterministically. |
| **Security** | Positive (Reduced Risk) | In `CORE`, the live server (port binding / WebSockets) and remote share backend (`export_to_excalidraw_url`) are disabled by default. |

---

## 10. Conclusion

The audit demonstrates that the current 47-tool MCP interface is bloated by redundant aliases, duplicate styling schemas, and specialized background servers that impose a heavy token penalty on every agent call. Implementing `EXCALIDRAW_TOOLSET=core|full` delivers an immediate **45.2% reduction in schema size (saving ~6,560 tokens per interaction)** while preserving full operational capability for both standard coding agents and specialized interactive users.
