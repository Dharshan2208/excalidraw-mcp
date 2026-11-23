"""CLI installer for agent skills in exca-mcp.

Copies packaged agent skills and references into user agent directories
(such as ~/.skills/ or project-local .skills/) with safety guards against
accidental overwrites, path traversal, and unsafe symlinks.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

from excalidraw_mcp.skills import (
    get_skill_metadata,
    iter_skill_files,
    list_skills,
)


class InstallAction(Enum):
    """Action to take for an individual skill file."""

    INSTALL = "INSTALL"
    SKIP = "SKIP"
    OVERWRITE = "OVERWRITE"


@dataclass
class FilePlan:
    """Planned action for a specific file during installation."""

    skill_name: str
    rel_path: str
    dest_path: Path
    action: InstallAction
    content: str
    reason: str = ""


@dataclass
class InstallResult:
    """Outcome of skill installation execution."""

    success: bool
    target_dir: Path
    installed_files: list[Path] = field(default_factory=list)
    skipped_files: list[Path] = field(default_factory=list)
    overwritten_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False


def validate_target_dir(target: str | Path) -> Path:
    """Validate and normalize destination directory path.

    Expands user home directory (~), resolves path, and rejects unsafe targets.
    """
    if not target:
        raise ValueError("Target directory path cannot be empty.")

    target_str = str(target).strip()
    if not target_str:
        raise ValueError("Target directory path cannot be whitespace.")

    # Expand ~ and resolve
    p = Path(target_str).expanduser()
    try:
        resolved = p.resolve()
    except Exception as e:
        raise ValueError(f"Invalid target path '{target}': {e}") from e

    # Disallow dangerous root paths
    if str(resolved) in ("/", "C:\\", "C:/"):
        raise ValueError("Installing skills directly into system root is not permitted.")

    return resolved


def plan_installation(
    target_dir: str | Path,
    force: bool = False,
) -> tuple[Path, list[FilePlan]]:
    """Generate the file-by-file plan for installing all skills and references.

    Args:
        target_dir: Path to directory where skills should be installed.
        force: If True, permit overwriting existing different files.

    Returns:
        Tuple of (validated_target_path, list_of_file_plans).
    """
    dest_root = validate_target_dir(target_dir)
    plans: list[FilePlan] = []
    skills = list_skills()

    for skill_name in skills:
        files = iter_skill_files(skill_name)
        for rel_path, content in files:
            dest_file = dest_root / skill_name / rel_path

            # Symlink safety check: ensure destination path does not escape dest_root
            try:
                resolved_dest = dest_file.resolve()
                resolved_root = dest_root.resolve()
                # Check whether destination resolves outside dest_root (M-027)
                if not (resolved_dest == resolved_root or resolved_dest.is_relative_to(resolved_root)):
                    plans.append(
                        FilePlan(
                            skill_name=skill_name,
                            rel_path=rel_path,
                            dest_path=dest_file,
                            action=InstallAction.SKIP,
                            content=content,
                            reason="Unsafe path or symlink escaping target directory.",
                        )
                    )
                    continue
            except Exception:
                pass

            if not dest_file.exists():
                plans.append(
                    FilePlan(
                        skill_name=skill_name,
                        rel_path=rel_path,
                        dest_path=dest_file,
                        action=InstallAction.INSTALL,
                        content=content,
                        reason="New file",
                    )
                )
            else:
                # File already exists
                try:
                    existing_content = dest_file.read_text(encoding="utf-8")
                except Exception:
                    existing_content = None

                if existing_content == content:
                    plans.append(
                        FilePlan(
                            skill_name=skill_name,
                            rel_path=rel_path,
                            dest_path=dest_file,
                            action=InstallAction.SKIP,
                            content=content,
                            reason="Identical content already present",
                        )
                    )
                elif force:
                    plans.append(
                        FilePlan(
                            skill_name=skill_name,
                            rel_path=rel_path,
                            dest_path=dest_file,
                            action=InstallAction.OVERWRITE,
                            content=content,
                            reason="Overwritten via --force",
                        )
                    )
                else:
                    plans.append(
                        FilePlan(
                            skill_name=skill_name,
                            rel_path=rel_path,
                            dest_path=dest_file,
                            action=InstallAction.SKIP,
                            content=content,
                            reason="Existing user content preserved (use --force to overwrite)",
                        )
                    )

    return dest_root, plans


def get_claude_skill_dir() -> Path:
    """Return default Claude Code skills directory (~/.claude/skills/ or $CLAUDE_CONFIG_DIR/skills/)."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir and config_dir.strip():
        return Path(config_dir.strip()).expanduser() / "skills"
    return Path.home() / ".claude" / "skills"


def _build_claude_skill_content() -> str:
    """Construct unified Claude Code SKILL.md reusing excalidraw-workflow instructions with Claude frontmatter and reference links."""
    from excalidraw_mcp.skills import get_skill_metadata, list_skills, read_skill_content

    raw_workflow = read_skill_content("excalidraw-workflow")
    # Strip existing frontmatter if present
    body = raw_workflow
    if raw_workflow.startswith("---"):
        parts = raw_workflow.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].lstrip()

    frontmatter = (
        "---\n"
        "name: excalidraw\n"
        "description: Create, edit, validate, and export professional Excalidraw diagrams using the exca-mcp MCP server. "
        "Use whenever an agent needs to create or modify architecture diagrams, flowcharts, or visual documentation.\n"
        "---\n\n"
    )

    # Append navigation index to bundled references and specialized skill guidelines
    ref_section = [
        "\n---\n",
        "## Bundled Reference Guidelines & Specialized Skills\n\n",
        "The following specialized reference documents are bundled in `./references/`:\n\n",
    ]
    for s_name in sorted(list_skills()):
        meta = get_skill_metadata(s_name)
        ref_section.append(f"### Skill: `{meta.name}`\n")
        ref_section.append(f"{meta.description}\n\n")
        if meta.reference_names:
            ref_section.append("Reference guides:\n")
            for ref_name in meta.reference_names:
                ref_section.append(f"- [{ref_name}](references/{ref_name}.md)\n")
            ref_section.append("\n")

    return frontmatter + body + "".join(ref_section)


def plan_claude_installation(
    target_dir: str | Path | None = None,
    force: bool = False,
) -> tuple[Path, list[FilePlan]]:
    """Generate the file-by-file plan for installing the Claude Code skill into target/excalidraw/.

    Args:
        target_dir: Path to directory where skills reside (default: ~/.claude/skills/ or $CLAUDE_CONFIG_DIR/skills/).
        force: If True, permit overwriting existing different files.

    Returns:
        Tuple of (validated_target_path, list_of_file_plans).
    """
    dest_root = validate_target_dir(target_dir if target_dir else get_claude_skill_dir())
    plans: list[FilePlan] = []
    skill_dir = dest_root / "excalidraw"

    # Main SKILL.md
    main_skill_content = _build_claude_skill_content()
    files_to_install: list[tuple[str, str]] = [("SKILL.md", main_skill_content)]

    # Collect reference files across all packaged skills
    seen_refs = set()
    for s_name in list_skills():
        for rel_path, content in iter_skill_files(s_name):
            if rel_path.startswith("references/") and rel_path not in seen_refs:
                seen_refs.add(rel_path)
                files_to_install.append((rel_path, content))

    for rel_path, content in files_to_install:
        dest_file = skill_dir / rel_path

        # Symlink safety check: ensure destination path does not escape dest_root
        try:
            resolved_dest = dest_file.resolve()
            resolved_root = dest_root.resolve()
            if not (resolved_dest == resolved_root or resolved_dest.is_relative_to(resolved_root)):
                plans.append(
                    FilePlan(
                        skill_name="excalidraw",
                        rel_path=rel_path,
                        dest_path=dest_file,
                        action=InstallAction.SKIP,
                        content=content,
                        reason="Unsafe path or symlink escaping target directory.",
                    )
                )
                continue
        except Exception:
            pass

        if not dest_file.exists():
            plans.append(
                FilePlan(
                    skill_name="excalidraw",
                    rel_path=rel_path,
                    dest_path=dest_file,
                    action=InstallAction.INSTALL,
                    content=content,
                    reason="New file",
                )
            )
        else:
            try:
                existing_content = dest_file.read_text(encoding="utf-8")
            except Exception:
                existing_content = None

            if existing_content == content:
                plans.append(
                    FilePlan(
                        skill_name="excalidraw",
                        rel_path=rel_path,
                        dest_path=dest_file,
                        action=InstallAction.SKIP,
                        content=content,
                        reason="Identical content already present",
                    )
                )
            elif force:
                plans.append(
                    FilePlan(
                        skill_name="excalidraw",
                        rel_path=rel_path,
                        dest_path=dest_file,
                        action=InstallAction.OVERWRITE,
                        content=content,
                        reason="Overwritten via --force",
                    )
                )
            else:
                plans.append(
                    FilePlan(
                        skill_name="excalidraw",
                        rel_path=rel_path,
                        dest_path=dest_file,
                        action=InstallAction.SKIP,
                        content=content,
                        reason="Existing user content preserved (use --force to overwrite)",
                    )
                )

    return dest_root, plans


def execute_installation(
    target_dir: str | Path | None = None,
    force: bool = False,
    dry_run: bool = False,
    is_claude: bool = False,
) -> InstallResult:
    """Execute installation plan with safety guards against partial failure.

    Args:
        target_dir: Target destination path.
        force: Overwrite existing files if True.
        dry_run: Preview only without modifying filesystem if True.
        is_claude: If True, install unified Claude Code CLI skill.

    Returns:
        InstallResult detailing all actions taken.
    """
    try:
        if is_claude:
            dest_root, plans = plan_claude_installation(target_dir, force=force)
        else:
            if not target_dir:
                raise ValueError("Target directory path cannot be empty.")
            dest_root, plans = plan_installation(target_dir, force=force)
    except Exception as e:
        return InstallResult(
            success=False,
            target_dir=Path(target_dir) if target_dir else Path("."),
            errors=[str(e)],
            dry_run=dry_run,
        )

    result = InstallResult(
        success=True,
        target_dir=dest_root,
        dry_run=dry_run,
    )

    if dry_run:
        for plan in plans:
            if plan.action == InstallAction.INSTALL:
                result.installed_files.append(plan.dest_path)
            elif plan.action == InstallAction.OVERWRITE:
                result.overwritten_files.append(plan.dest_path)
            else:
                result.skipped_files.append(plan.dest_path)
        return result

    # Execute file writes
    for plan in plans:
        if plan.action == InstallAction.SKIP:
            result.skipped_files.append(plan.dest_path)
            continue

        try:
            # Ensure parent directories exist
            plan.dest_path.parent.mkdir(parents=True, exist_ok=True)
            plan.dest_path.write_text(plan.content, encoding="utf-8")

            if plan.action == InstallAction.INSTALL:
                result.installed_files.append(plan.dest_path)
            elif plan.action == InstallAction.OVERWRITE:
                result.overwritten_files.append(plan.dest_path)
        except Exception as e:
            result.errors.append(f"Failed to write '{plan.dest_path}': {e}")
            result.success = False

    return result


def format_list_output() -> str:
    """Format available skills and reference documents for listing."""
    lines = ["Available Agent Skills in exca-mcp:", "=" * 50]
    skills = list_skills()

    for skill_name in skills:
        meta = get_skill_metadata(skill_name)
        lines.append(f"\n  • {meta.name}")
        if meta.description:
            lines.append(f"    Description: {meta.description}")
        if meta.reference_names:
            lines.append(f"    References ({len(meta.reference_names)}):")
            for ref in meta.reference_names:
                lines.append(f"      - references/{ref}.md")

    lines.append(f"\nTotal: {len(skills)} skills available for installation.")
    return "\n".join(lines)


def run_install_skills_cli(argv: Sequence[str] | None = None) -> int:
    """CLI subcommand entry point for `exca-mcp install-skills`."""
    parser = argparse.ArgumentParser(
        prog="exca-mcp install-skills",
        description="Install packaged agent skills and reference documents into your AI agent's directory.",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=str,
        help="Target directory (e.g. ~/.skills/, ~/.agents/skills/, or project .skills/)",
    )
    parser.add_argument(
        "--dir",
        "-d",
        type=str,
        dest="target_dir_alias",
        help="Alias for --target directory",
    )
    parser.add_argument(
        "--claude",
        action="store_true",
        help="Install Claude Code CLI skill into ~/.claude/skills/excalidraw/ (or $CLAUDE_CONFIG_DIR/skills/excalidraw/)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Permit overwriting existing skill files",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Display planned actions without making any filesystem modifications",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List all packaged skills and reference documents without installing",
    )

    args = parser.parse_args(argv)

    if args.list:
        print(format_list_output())
        return 0

    target = args.target or args.target_dir_alias
    if not args.claude and not target:
        print("Error: --target directory is required for installation (or specify --claude).\n", file=sys.stderr)
        print("Quick options:", file=sys.stderr)
        print("  • Claude Code CLI:   exca-mcp install-skills --claude", file=sys.stderr)
        print("  • Custom Directory:  exca-mcp install-skills --target <path>", file=sys.stderr)
        print("  • List Skills:       exca-mcp install-skills --list\n", file=sys.stderr)
        print("Run 'exca-mcp install-skills --help' for details.", file=sys.stderr)
        return 1

    planner = plan_claude_installation if args.claude else plan_installation
    try:
        dest_root, plans = planner(target_dir=target, force=args.force)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    prefix = "[DRY-RUN] " if args.dry_run else ""
    print(f"{prefix}Planning installation to: {dest_root}")

    # Display actions
    for plan in plans:
        rel_to_target = plan.dest_path.relative_to(dest_root)
        if plan.action == InstallAction.INSTALL:
            print(f"  {prefix}[INSTALL]   {rel_to_target}")
        elif plan.action == InstallAction.OVERWRITE:
            print(f"  {prefix}[OVERWRITE] {rel_to_target} ({plan.reason})")
        else:
            print(f"  {prefix}[SKIP]      {rel_to_target} ({plan.reason})")

    result = execute_installation(target, force=args.force, dry_run=args.dry_run, is_claude=args.claude)

    print("\n" + "=" * 50)
    if result.dry_run:
        print(
            f"Dry run complete. Would install: {len(result.installed_files)}, "
            f"Would overwrite: {len(result.overwritten_files)}, "
            f"Would skip: {len(result.skipped_files)}."
        )
    else:
        print(
            f"Installation complete. Installed: {len(result.installed_files)}, "
            f"Overwritten: {len(result.overwritten_files)}, "
            f"Skipped: {len(result.skipped_files)}."
        )
        print(f"Destination: {result.target_dir}")

    if result.errors:
        print("\nErrors encountered:", file=sys.stderr)
        for err in result.errors:
            print(f"  • {err}", file=sys.stderr)
        return 1

    return 0 if result.success else 1
