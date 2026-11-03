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
