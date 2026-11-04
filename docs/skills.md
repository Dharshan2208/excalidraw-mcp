# Agent Skills Distribution

`exca-mcp` ships with **six production-quality Agent Skills** and supporting reference documents designed to teach AI agents how to produce clean, human-crafted diagrams that are easy to open and edit in [excalidraw.com](https://excalidraw.com).

To ensure every user can access these skills regardless of environment, `exca-mcp` provides **three unified distribution mechanisms**:

1. **PyPI Package Distribution**: All skills and references are bundled inside the published Python package. No git checkout or cloning is required.
2. **MCP Resources & Prompts**: Connected AI clients can discover and read skill instructions directly over the MCP protocol without accessing the local filesystem.
3. **CLI Skill Installer (`exca-mcp install-skills`)**: Users can install the skills and reference directories into their coding agent's local directory with a single command.

---

### A. PyPI Package Distribution

All six skills and their nested reference guides are packaged directly inside the `exca-mcp` wheel and source distributions under `excalidraw_mcp/skills/`.

When you install `exca-mcp` via `uvx` or `pip`, all skill assets are bundled automatically:

```bash
# Ephemeral execution via uvx (fetches package and bundled skills)
uvx exca-mcp

# Or standard pip installation
pip install exca-mcp
```

At runtime, `exca-mcp` resolves skill instructions using Python's `importlib.resources` API, guaranteeing access across wheels, source checkouts, and isolated virtual environments without relying on internet access or GitHub availability.

The packaged skills hierarchy:
```
excalidraw_mcp/skills/
├── architecture-diagrams/
│   ├── SKILL.md
│   └── references/
│       └── architecture-patterns.md
├── diagram-planning/
│   ├── SKILL.md
│   └── references/
│       └── entry-tool-decision-tree.md
├── excalidraw-workflow/
│   └── SKILL.md
├── flowcharts-and-processes/
│   ├── SKILL.md
│   └── references/
│       └── flowchart-patterns.md
├── human-style-and-polish/
│   ├── SKILL.md
│   └── references/
│       ├── anti-patterns.md
│       └── palette-catalog.md
└── verify-and-editable-handoff/
    ├── SKILL.md
    └── references/
        └── delivery-checklist.md
```

---

### B. MCP Resources & Prompts

When connected to an MCP host, `exca-mcp` exposes the complete skills library through standard MCP Resources and reusable Prompts.

#### 1. Skill Discovery Index
- **`exca-mcp://skills/index`** (`application/json`): A catalog listing all available skills, summaries, supporting references, cross-skill relationships, and recommended workflow pipelines.

#### 2. Individual Skill Resources (`text/markdown`)
Agents can fetch the complete `SKILL.md` instructions for any skill via stable URIs:
- `exca-mcp://skills/architecture-diagrams`: Multi-tier cloud, distributed backend, and infrastructure architecture design.
- `exca-mcp://skills/diagram-planning`: Upfront planning, density capping ($\le 15$ nodes), layout tiering, and entry tool selection.
- `exca-mcp://skills/excalidraw-workflow`: Foundational MCP tool usage, element creation, and active canvas operations.
- `exca-mcp://skills/flowcharts-and-processes`: Flowcharts, decision trees, CI/CD pipelines, and state machines.
- `exca-mcp://skills/human-style-and-polish`: Organic hand-drawn aesthetics, 60-30-10 semantic palettes, typography hierarchy, and geometric clearances.
- `exca-mcp://skills/verify-and-editable-handoff`: 5-step quality gate, geometry diagnostics, visual PNG preview inspection, and dual format export.

#### 3. Reference Resources (`text/markdown`)
Detailed visual catalogs and geometric specifications are accessible individually:
- `exca-mcp://skills/architecture-diagrams/references/architecture-patterns`: Coordinate systems, tier grids, side columns, and component dimensions.
- `exca-mcp://skills/diagram-planning/references/entry-tool-decision-tree`: Decision tree and tradeoff matrix for selecting the right MCP entry tool.
- `exca-mcp://skills/flowcharts-and-processes/references/flowchart-patterns`: Terminal shapes, diamond dimensions, decision outlets, and perimeter loops.
- `exca-mcp://skills/human-style-and-polish/references/anti-patterns`: Common visual defects (rainbow colors, cramped frames, diagonal crossings) and immediate fixes.
- `exca-mcp://skills/human-style-and-polish/references/palette-catalog`: Restrained semantic color palettes (Cloud Architecture, Editorial Product, Security Enclave).
- `exca-mcp://skills/verify-and-editable-handoff/references/delivery-checklist`: 10-point pre-delivery verification checklist.

#### 4. Task-Oriented MCP Prompts
The server registers 5 reusable prompts that guide agents through end-to-end diagramming tasks:
- **`create_architecture_diagram`**: Guides the agent through a strict 10-step process (inspect codebase, plan tiers, construct via primitives, diagnose geometry, auto-repair, preview PNG, and export `.excalidraw` and `.png`).
- **`create_flowchart`**: Guides construction of flowcharts with single starts, clear terminals, labeled decision diamonds, and perimeter loops.
- **`plan_diagram`**: Prompts the agent to formulate a written architectural plan before making drawing tool calls.
- **`edit_existing_diagram`**: Guides non-destructive updates to active or saved diagrams while preserving existing layout and hierarchy.
- **`verify_and_export_diagram`**: Guides the final 5-step quality gate: diagnose layout, auto-repair, visual PNG preview, human editability check, and dual export.

> **:** > MCP Prompts and Resources provide standardized, discoverable instructions. However, automatic background skill activation depends on your specific MCP client's capabilities. If your client does not auto-load resources into agent context, use the CLI Installer below.

---

### C. CLI Skills Installer (`exca-mcp install-skills`)

Users who prefer local skill files can install all six skills and reference documents directly into their AI agent's directory using the CLI installer.

#### Basic Usage

Install all skills into a global agent skills directory:
```bash
# Using uvx without installing exca-mcp globally
uvx exca-mcp install-skills --target ~/.skills/

# Or using an existing pip installation
exca-mcp install-skills --target ~/.skills/
```

Install into a project-local or custom agent directory:
```bash
# Project-local directory
exca-mcp install-skills --target .skills/

# Custom AI agent directory (e.g., Cursor, Claude, Antigravity)
exca-mcp install-skills --target ~/.agents/skills/
```

#### Safe Overwrite Controls

The installer includes strict safety guards to protect user modifications:
- **Default Protection**: Existing files are skipped automatically. The installer will never silently overwrite customized user files.
- **Idempotent**: Re-running the command skips identical files with zero side effects.
- **Force Replacement**: Use `--force` to explicitly replace existing files with the packaged canonical versions:
  ```bash
  exca-mcp install-skills --target ~/.skills/ --force
  ```
- **Dry-Run Preview**: Preview exactly which files would be installed, skipped, or overwritten without modifying the filesystem:
  ```bash
  exca-mcp install-skills --target ~/.skills/ --dry-run
  ```
- **List Available Skills**: Inspect all packaged skills and reference files:
  ```bash
  exca-mcp install-skills --list
  ```

---

---
