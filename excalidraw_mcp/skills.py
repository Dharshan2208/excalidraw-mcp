"""Agent skills loader and management utilities for exca-mcp.

Provides unified runtime access to packaged and local agent skills,
supporting git checkouts, installed wheels, editable installs, and uvx execution.
"""

from __future__ import annotations

import importlib.resources as pkg_resources
import os
import re
from dataclasses import dataclass, field
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

# Pattern for safe skill names and reference file names (prevents path traversal)
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_-]+(?:\.md)?$")


class SkillError(Exception):
    """Base exception for skill loading and resolution errors."""


class SkillNotFoundError(SkillError, KeyError):
    """Raised when a requested skill does not exist."""


class ReferenceNotFoundError(SkillError, KeyError):
    """Raised when a requested reference document does not exist."""


class InvalidSkillNameError(SkillError, ValueError):
    """Raised when an invalid or unsafe skill or reference name is provided."""


@dataclass(frozen=True)
class SkillMetadata:
    """Metadata describing an agent skill."""

    name: str
    description: str
    has_skill_file: bool
    reference_names: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Skill:
    """Fully loaded agent skill with instructions and reference documents."""

    name: str
    description: str
    content: str
    references: dict[str, str] = field(default_factory=dict)

    @property
    def reference_names(self) -> list[str]:
        return sorted(self.references.keys())


def _validate_skill_name(name: str) -> str:
    """Validate that a skill name contains only safe characters."""
    if not name or not isinstance(name, str):
        raise InvalidSkillNameError("Skill name must be a non-empty string.")
    name = name.strip()
    if not _SAFE_NAME_RE.match(name):
        raise InvalidSkillNameError(
            f"Invalid skill name '{name}'. Names must only contain alphanumeric characters, underscores, and hyphens."
        )
    return name


def _validate_reference_name(name: str) -> str:
    """Validate that a reference document name is safe and normalize extension."""
    if not name or not isinstance(name, str):
        raise InvalidSkillNameError("Reference name must be a non-empty string.")
    name = name.strip()
    if not _SAFE_REF_RE.match(name):
        raise InvalidSkillNameError(
            f"Invalid reference name '{name}'. Names must only contain alphanumeric characters, underscores, and hyphens."
        )
    if name.endswith(".md"):
        name = name[:-3]
    return name


def _parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter and body from markdown content."""
    frontmatter: dict[str, str] = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_fm = parts[1].strip()
            body = parts[2].lstrip()
            for line in raw_fm.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    val = val.strip()
                    # Strip enclosing quotes if present
                    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                        val = val[1:-1]
                    frontmatter[key.strip()] = val

    return frontmatter, body


def get_skills_root() -> Traversable | Path:
    """Resolve the root skills directory across diverse execution environments.

    Checks:
    1. EXCALIDRAW_SKILLS_DIR environment variable override.
    2. Packaged importlib.resources directory (`excalidraw_mcp.skills`).
    3. Git checkout / editable source repository fallback (`.skills` directory).
    """
    # 1. Environment variable override
    env_dir = os.environ.get("EXCALIDRAW_SKILLS_DIR")
    if env_dir:
        p = Path(env_dir).resolve()
        if p.is_dir():
            return p

    # 2. Packaged resources (inside installed wheel / site-packages)
    try:
        packaged = pkg_resources.files("excalidraw_mcp").joinpath("skills")
        if packaged.is_dir():
            # Verify it actually contains skill directories
            items = [item for item in packaged.iterdir() if item.is_dir()]
            if items:
                return packaged
    except Exception:
        pass

    # 3. Source repository root (.skills directory)
    src_skills = Path(__file__).resolve().parent.parent / ".skills"
    if src_skills.is_dir():
        return src_skills

    # 4. Fallback: return packaged Traversable even if empty to preserve interface
    return pkg_resources.files("excalidraw_mcp").joinpath("skills")


def list_skills() -> list[str]:
    """Return a sorted list of all available skill names."""
    root = get_skills_root()
    skills: list[str] = []

    try:
        for item in root.iterdir():
            if item.is_dir():
                skill_file = item.joinpath("SKILL.md")
                if skill_file.is_file():
                    skills.append(item.name)
    except Exception:
        return []

    return sorted(skills)


def _get_skill_dir(name: str) -> Traversable | Path:
    """Retrieve the Traversable/Path for a specific skill directory."""
    clean_name = _validate_skill_name(name)
    root = get_skills_root()
    skill_dir = root.joinpath(clean_name)

    if not skill_dir.is_dir():
        raise SkillNotFoundError(f"Skill '{clean_name}' not found.")

    skill_file = skill_dir.joinpath("SKILL.md")
    if not skill_file.is_file():
        raise SkillNotFoundError(f"Skill '{clean_name}' is missing SKILL.md.")

    return skill_dir


def get_skill_metadata(name: str) -> SkillMetadata:
    """Retrieve metadata for a skill without loading all reference bodies."""
    clean_name = _validate_skill_name(name)
    skill_dir = _get_skill_dir(clean_name)

    skill_file = skill_dir.joinpath("SKILL.md")
    content = skill_file.read_text(encoding="utf-8")
    fm, _ = _parse_frontmatter(content)
    description = fm.get("description", "")

    ref_names: list[str] = []
    ref_dir = skill_dir.joinpath("references")
    if ref_dir.is_dir():
        for f in ref_dir.iterdir():
            if f.is_file() and f.name.endswith(".md"):
                ref_names.append(f.name[:-3])

    return SkillMetadata(
        name=clean_name,
        description=description,
        has_skill_file=True,
        reference_names=tuple(sorted(ref_names)),
    )


def list_skill_references(skill_name: str) -> list[str]:
    """List all available reference document slugs for a skill."""
    return list(get_skill_metadata(skill_name).reference_names)


def read_skill_content(name: str) -> str:
    """Read the complete raw markdown content of a skill's SKILL.md."""
    clean_name = _validate_skill_name(name)
    skill_dir = _get_skill_dir(clean_name)
    skill_file = skill_dir.joinpath("SKILL.md")
    return skill_file.read_text(encoding="utf-8")


def read_reference_content(skill_name: str, reference_name: str) -> str:
    """Read the complete raw markdown content of a skill's reference document."""
    clean_skill = _validate_skill_name(skill_name)
    clean_ref = _validate_reference_name(reference_name)

    skill_dir = _get_skill_dir(clean_skill)
    ref_dir = skill_dir.joinpath("references")
    if not ref_dir.is_dir():
        raise ReferenceNotFoundError(
            f"Reference '{clean_ref}' not found (skill '{clean_skill}' has no references directory)."
        )

    ref_file = ref_dir.joinpath(f"{clean_ref}.md")
    if not ref_file.is_file():
        raise ReferenceNotFoundError(
            f"Reference '{clean_ref}' not found in skill '{clean_skill}'."
        )

    return ref_file.read_text(encoding="utf-8")


def load_skill(name: str) -> Skill:
    """Load a complete skill with all its reference documents."""
    clean_name = _validate_skill_name(name)
    metadata = get_skill_metadata(clean_name)
    content = read_skill_content(clean_name)

    references: dict[str, str] = {}
    for ref_name in metadata.reference_names:
        references[ref_name] = read_reference_content(clean_name, ref_name)

    return Skill(
        name=clean_name,
        description=metadata.description,
        content=content,
        references=references,
    )


def get_all_skills() -> dict[str, Skill]:
    """Load all available skills into a dictionary keyed by skill name."""
    return {name: load_skill(name) for name in list_skills()}


def iter_skill_files(skill_name: str) -> list[tuple[str, str]]:
    """Return all relative file paths and text contents for a skill.

    Returns:
        List of tuples: (relative_path, content)
        e.g. [("SKILL.md", content), ("references/palette-catalog.md", content)]
    """
    clean_name = _validate_skill_name(skill_name)
    skill_dir = _get_skill_dir(clean_name)
    files: list[tuple[str, str]] = []

    # 1. Root SKILL.md
    skill_file = skill_dir.joinpath("SKILL.md")
    files.append(("SKILL.md", skill_file.read_text(encoding="utf-8")))

    # 2. References
    ref_dir = skill_dir.joinpath("references")
    if ref_dir.is_dir():
        for ref_item in sorted(ref_dir.iterdir(), key=lambda x: x.name):
            if ref_item.is_file() and ref_item.name.endswith(".md"):
                rel_path = f"references/{ref_item.name}"
                files.append((rel_path, ref_item.read_text(encoding="utf-8")))

    return files


# Skill relationship map for index and client guidance
SKILL_RELATIONSHIPS: dict[str, dict[str, Any]] = {
    "diagram-planning": {
        "role": "Upfront planning, scope control, tiering, palette selection, and tool selection",
        "recommended_first": True,
        "leads_to": ["architecture-diagrams", "flowcharts-and-processes"],
    },
    "architecture-diagrams": {
        "role": "Production system, multi-tier cloud, and distributed infrastructure architecture",
        "recommended_first": False,
        "prerequisites": ["diagram-planning"],
        "leads_to": ["human-style-and-polish", "verify-and-editable-handoff"],
    },
    "flowcharts-and-processes": {
        "role": "Business logic, decision trees, CI/CD pipelines, and state machines",
        "recommended_first": False,
        "prerequisites": ["diagram-planning"],
        "leads_to": ["human-style-and-polish", "verify-and-editable-handoff"],
    },
    "human-style-and-polish": {
        "role": "Hand-drawn aesthetic, typography hierarchy, restrained palettes, and verified clearances",
        "recommended_first": False,
        "prerequisites": ["architecture-diagrams", "flowcharts-and-processes"],
        "leads_to": ["verify-and-editable-handoff"],
    },
    "verify-and-editable-handoff": {
        "role": "Layout diagnostics, auto-repair, visual PNG preview, human editability, and dual export",
        "recommended_first": False,
        "prerequisites": ["human-style-and-polish"],
        "terminal": True,
    },
    "excalidraw-workflow": {
        "role": "Comprehensive MCP tool usage, element creation, and active canvas manipulation",
        "recommended_first": False,
        "general_reference": True,
    },
}


def get_skills_index() -> dict[str, Any]:
    """Generate structured discovery index of all skills and references."""
    skills_data = []
    all_names = list_skills()

    for name in all_names:
        meta = get_skill_metadata(name)
        rel = SKILL_RELATIONSHIPS.get(name, {})
        skills_data.append(
            {
                "name": meta.name,
                "description": meta.description,
                "resource_uri": f"exca-mcp://skills/{meta.name}",
                "references": [
                    {
                        "name": ref,
                        "resource_uri": f"exca-mcp://skills/{meta.name}/references/{ref}",
                    }
                    for ref in meta.reference_names
                ],
                "relationships": rel,
            }
        )

    return {
        "total_skills": len(skills_data),
        "skills": skills_data,
        "recommended_workflow": [
            "1. diagram-planning (define scope, tiers, colors, and layout)",
            "2. architecture-diagrams OR flowcharts-and-processes (construct structure and bindings)",
            "3. human-style-and-polish (refine typography, strokes, and clearances)",
            "4. verify-and-editable-handoff (diagnose geometry, preview PNG, export files)",
        ],
    }


def register_skills_mcp(mcp: Any) -> None:
    """Register skills resources and task-oriented prompts with a FastMCP server."""
    import json

    # 1. Discovery Index Resource
    @mcp.resource(
        "exca-mcp://skills/index",
        mime_type="application/json",
        description="Discovery index of available agent skills, supporting reference documents, and recommended workflows.",
    )
    def skills_index() -> str:
        """Structured catalog of all available agent skills, reference documents, and usage flows."""
        return json.dumps(get_skills_index(), indent=2)

    # 2. Static Resources for every skill and reference
    for skill_name in list_skills():
        meta = get_skill_metadata(skill_name)

        def _bind_skill(s_name: str, s_desc: str):
            @mcp.resource(
                f"exca-mcp://skills/{s_name}",
                mime_type="text/markdown",
                name=f"skill_{s_name}",
                description=f"Skill: {s_name} — {s_desc}",
            )
            def _skill_resource() -> str:
                return read_skill_content(s_name)

            return _skill_resource

        _bind_skill(skill_name, meta.description)

        for ref_name in meta.reference_names:
            def _bind_ref(s_name: str, r_name: str):
                @mcp.resource(
                    f"exca-mcp://skills/{s_name}/references/{r_name}",
                    mime_type="text/markdown",
                    name=f"ref_{s_name}_{r_name}",
                    description=f"Reference: {r_name} for skill {s_name}",
                )
                def _ref_resource() -> str:
                    return read_reference_content(s_name, r_name)

                return _ref_resource

            _bind_ref(skill_name, ref_name)

    # 3. MCP Prompts

    @mcp.prompt(
        description="Comprehensive 10-step workflow to plan, construct, validate, and export a production architecture diagram."
    )
    def create_architecture_diagram(
        system_description: str,
        style: str = "modern",
        output_name: str = "architecture",
    ) -> str:
        """Prompt guiding an AI agent to design and export a multi-tier system architecture diagram."""
        arch_skill = read_skill_content("architecture-diagrams")
        polish_skill = read_skill_content("human-style-and-polish")
        handoff_skill = read_skill_content("verify-and-editable-handoff")

        return f"""# Architecture Diagram Creation Task

Target System: {system_description}
Preferred Style: {style}
Export Base Name: {output_name}

You are acting as a Principal Software Architect. Follow this strict 10-step process to design, create, and verify the architecture diagram using exca-mcp tools:

## 1. Inspect and Understand
- Inspect the actual project codebase, services, data stores, external dependencies, and network boundaries.
- Identify major architectural layers: Clients, Edge/Ingress, Application Services, Persistence/Storage, and External Integrations.

## 2. Architectural Planning & Tiering
- Cap component density: maximum 12-15 core nodes. Split into sub-diagrams if the topology is larger.
- Establish clean vertical or horizontal tiers:
  * Tier 1 (Clients / Presentation)
  * Tier 2 (Gateway / Load Balancing)
  * Tier 3 (Microservices / Business Logic)
  * Tier 4 (Databases, Caches, Event Queues)
  * Tier 5 (External APIs / Third-Party Services)

## 3. Visual Craftsmanship & Semantic Palette
- Apply the 60-30-10 palette rule:
  * 60% Neutrals (canvas white `#ffffff`, frame background `#f8f9fa`, slate text `#212529`).
  * 30% Structural Primary (core services: Soft Blue `#e7f5ff`, stroke `#1971c2`).
  * 10% Intentional Accents (Storage: Mint `#e6fcf5`, Queues: Amber `#fff9db`, External/Warnings: Coral `#fff5f5`).
- Typography hierarchy: 28px title, 20px frame headers, 16px service labels, 12-14px protocol subtext.
- Grid clearances: maintain >= 30px gap between sibling shapes, 15px clearance around connector corridors, and >= 40px internal frame padding.

## 4. Construction via Primitives
- Use `add_frame(name, x, y, w, h)` to establish physical and logical deployment boundaries.
- Use `add_rectangle(x, y, w, h, label="Title\\nSubtitle", frame_id=...)` to create components.
- Use `connect(source_id, target_id, label="Protocol", elbowed=True)` to create bound, orthogonal connectors.
  * Solid lines (`strokeStyle="solid"`) for synchronous HTTP/gRPC.
  * Dashed lines (`strokeStyle="dashed"`) for asynchronous events, Kafka topics, or message queues.

## 5. Geometry Verification & Auto-Repair
- Call `auto_fix_layout(dry_run=True, repair_scope="all", min_gap=30.0)` to check for overlaps or spacing violations.
- If issues exist, apply `auto_fix_layout(dry_run=False, aggressiveness="balanced", min_gap=30.0)`.

## 6. Visual Preview Inspection
- Call `preview(scale=1.0, padding=40, background=True)` and visually inspect the rendered PNG to verify visual balance and contrast.

## 7. Delivery & Human Editability
- Verify editability: all connectors must have bound endpoints (`source_id`, `target_id`), labels bound inside shapes, and no locked elements.
- Save native editable document snapshot: `save(name="{output_name}", overwrite=True)`.
- Export high-resolution PNG: `export_png(name="{output_name}", scale=2.0, overwrite=True)`.

---
### Supporting Reference Skills
- Architecture Patterns: exca-mcp://skills/architecture-diagrams
- Human Polish & Palette: exca-mcp://skills/human-style-and-polish
- Verification Checklist: exca-mcp://skills/verify-and-editable-handoff
"""

    @mcp.prompt(
        description="Prompt guiding an AI agent to design a clean, professional flowchart, pipeline, or decision logic diagram."
    )
    def create_flowchart(
        process_description: str,
        direction: str = "TB",
        output_name: str = "flowchart",
    ) -> str:
        """Prompt guiding an AI agent to construct a flowchart or process diagram."""
        return f"""# Flowchart & Process Diagram Task

Process Description: {process_description}
Primary Flow Direction: {direction} (Top-to-Bottom: TB, Left-to-Right: LR)
Export Base Name: {output_name}

Follow these professional flowchart rules using exca-mcp tools:

1. Single Start Node: Exactly one entry point styled as a soft green pill (`roundness="round"`, backgroundColor="#e6fcf5", strokeColor="#0ca678").
2. Explicit Decision Diamonds: Use `add_diamond` strictly for conditional branches. Phrased as questions ending with `?`. Minimum dimensions 180x110px.
3. Labeled Outlets: Every connector exiting a diamond MUST have an explicit label (`"Yes"`, `"No"`, `"Retry"`, `"Timeout"`).
4. Distinct Terminals: End every path with a terminal (Success in mint green `#ebfbee`, Failure/Abort in light red `#fff5f5`).
5. Orthogonal Routing: Set `elbowed=True` on all `connect` calls.
6. Perimeter Loops: Route retry or feedback loops around the exterior perimeter (>= 60px lateral clearance from trunk).
7. Verification & Delivery:
   - Run `auto_fix_layout(dry_run=True)` to confirm 0 defects.
   - Inspect visual rendering with `preview(scale=1.0)`.
   - Save native scene `save(name="{output_name}", overwrite=True)` and export `export_png(name="{output_name}", overwrite=True)`.

Reference: exca-mcp://skills/flowcharts-and-processes
"""

    @mcp.prompt(
        description="Formulate a written architectural plan, node inventory, tier breakdown, and palette selection before drawing."
    )
    def plan_diagram(
        request: str,
        diagram_type: str = "architecture",
    ) -> str:
        """Prompt guiding the upfront planning phase before invoking drawing tools."""
        return f"""# Diagram Planning Task

Raw Request: {request}
Target Type: {diagram_type}

Before making any drawing tool calls, create a written diagram plan covering:

1. Audience & Intent: Who will read this diagram (executives, engineers, customers) and what decision or understanding does it support?
2. Node Inventory & Density Cap:
   - List every component, service, data store, and boundary.
   - Count nodes: if > 15 nodes, partition into high-level system overview + focused sub-system diagrams.
3. Layer Tiering & Flow Direction:
   - Identify tiers (Clients, Gateway, Microservices, Storage, Third-party).
   - Choose flow direction (Top-to-Bottom for multi-tier systems, Left-to-Right for event pipelines).
4. Entry Tool Justification:
   - Select and justify tool: Primitives (`add_frame`, `add_rectangle`, `connect`) for multi-tier production architecture, `draw_mermaid` for quick sequential pipelines.
5. Semantic Palette Plan (60-30-10):
   - 60% Neutrals (containers, borders, body text).
   - 30% Structural Primary (core services).
   - 10% Intentional Accent (data, queues, warnings).

Reference: exca-mcp://skills/diagram-planning
"""

    @mcp.prompt(
        description="Safely inspect and modify an existing Excalidraw scene while preserving layout structure and visual balance."
    )
    def edit_existing_diagram(
        instructions: str,
        scene_name: str = "",
    ) -> str:
        """Prompt guiding non-destructive edits to an active or loaded Excalidraw diagram."""
        load_instruction = (
            f"1. First load the target scene: `load(name='{scene_name}')`."
            if scene_name
            else "1. Inspect the currently active canvas."
        )

        return f"""# Edit Existing Diagram Task

Edit Instructions: {instructions}
Target Scene: {scene_name or "active canvas"}

Perform targeted, non-destructive modifications to the diagram:

{load_instruction}
2. Call `get_scene()` to retrieve active elements, their IDs, positions, and connections.
3. Plan minimal required mutations:
   - To update labels or styles: call `update_element(element_id=..., ...)`.
   - To reposition components: call `move(element_id=..., x=..., y=...)` (attached bound connectors will follow).
   - To remove elements: call `delete(element_id=...)`.
   - To connect new relationships: call `connect(source_id=..., target_id=..., label=..., elbowed=True)`.
4. Maintain visual hierarchy and grid spacing: do not cause accidental overlaps or frame boundary escapes.
5. Validate layout: run `auto_fix_layout(dry_run=True)` to confirm zero introduced defects.
6. Check visual appearance with `preview(scale=1.0)`.
7. Save snapshot: `save(name=..., overwrite=True)`.

Reference: exca-mcp://skills/excalidraw-workflow
"""

    @mcp.prompt(
        description="Comprehensive 5-step quality gate: diagnose layout, auto-repair, visual preview inspection, and dual export."
    )
    def verify_and_export_diagram(
        output_name: str = "diagram",
        directory: str = "docs",
    ) -> str:
        """Prompt guiding the final verification and export of an Excalidraw diagram."""
        return f"""# Diagram Verification and Delivery Task

Target Name: {output_name}
Target Directory: {directory}

Execute this quality gate before completing the diagram task:

1. Step 1: Geometry Diagnostics
   - Run `auto_fix_layout(dry_run=True, repair_scope='all', min_gap=30.0)`.
   - If `status != 'no_changes_needed'`, inspect `initial_issues`.
2. Step 2: Auto-Repair
   - If defects exist, run `auto_fix_layout(dry_run=False, repair_scope='all', aggressiveness='balanced', min_gap=30.0)`.
   - If changes are unsatisfactory, invoke `undo()` immediately.
3. Step 3: Visual Inspection
   - Call `preview(scale=1.0, padding=40, background=True)`.
   - Visually check alignment, typography readability (>= 14px), frame padding (>= 40px), and connector clarity.
4. Step 4: Human Editability Audit
   - Confirm all connectors use bound endpoints (`source_id`, `target_id`).
   - Confirm shape labels are bound to their host elements.
   - Ensure no elements remain locked.
5. Step 5: Dual Format Export
   - Save native editable file: `save(name='{output_name}', overwrite=True)` or export scene JSON via `export_scene()`.
   - Export high-resolution PNG: `export_png(name='{output_name}', directory='{directory}', scale=2.0, overwrite=True)`.

Reference: exca-mcp://skills/verify-and-editable-handoff
"""
