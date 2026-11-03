"""Tests for CLI agent skills installer."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

from excalidraw_mcp.installer import (
    InstallAction,
    execute_installation,
    plan_installation,
    run_install_skills_cli,
    validate_target_dir,
)
from excalidraw_mcp.skills import read_reference_content, read_skill_content
from tests.test_skills_distribution import (
    EXPECTED_REFERENCES,
    EXPECTED_SKILLS,
)


def test_validate_target_dir():
    """Verify target directory validation, expansion, and security checks."""
    # Home expansion
    home_path = validate_target_dir("~/.skills")
    assert str(home_path).startswith(str(Path.home()))

    # Empty target raises ValueError
    with pytest.raises(ValueError):
        validate_target_dir("")

    with pytest.raises(ValueError):
        validate_target_dir("   ")

    # Root target is forbidden
    with pytest.raises(ValueError):
        validate_target_dir("/")


def test_install_to_nonexistent_directory():
    """Verify installation creates all 6 skills and 6 references in a fresh directory."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "new_skills"
        assert not target.exists()

        result = execute_installation(target, force=False, dry_run=False)
        assert result.success is True
        assert len(result.errors) == 0

        # 6 SKILL.md files + 6 reference files = 12 total files
        assert len(result.installed_files) == 12
        assert len(result.skipped_files) == 0
        assert len(result.overwritten_files) == 0

        # Verify all 6 skills exist
        for skill_name in EXPECTED_SKILLS:
            skill_md = target / skill_name / "SKILL.md"
            assert skill_md.is_file(), f"Missing {skill_md}"
            assert skill_md.read_text(encoding="utf-8") == read_skill_content(skill_name)

            for ref in EXPECTED_REFERENCES[skill_name]:
                ref_md = target / skill_name / "references" / f"{ref}.md"
                assert ref_md.is_file(), f"Missing {ref_md}"
                assert ref_md.read_text(encoding="utf-8") == read_reference_content(
                    skill_name, ref
                )


def test_dry_run_makes_no_filesystem_changes():
    """Verify that --dry-run previews actions without creating directories or files."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "dry_run_target"
        assert not target.exists()

        result = execute_installation(target, force=False, dry_run=True)
        assert result.success is True
        assert result.dry_run is True
        assert len(result.installed_files) == 12

        # Crucial check: target directory must NOT be created
        assert not target.exists()


def test_repeated_installation_skips_identical_content():
    """Verify idempotency: re-running installation skips identical files without modifying them."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "idempotent_target"

        # First install
        r1 = execute_installation(target, force=False)
        assert r1.success is True
        assert len(r1.installed_files) == 12

        # Second install (idempotent run)
        r2 = execute_installation(target, force=False)
        assert r2.success is True
        assert len(r2.installed_files) == 0
        assert len(r2.skipped_files) == 12
        assert len(r2.overwritten_files) == 0


def test_skip_modified_user_files_without_force():
    """Verify safety: existing modified files are preserved and never overwritten without --force."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "custom_target"
        execute_installation(target, force=False)

        custom_file = target / "architecture-diagrams" / "SKILL.md"
        custom_content = "# My Custom User Architect Skill\nDo not overwrite!"
        custom_file.write_text(custom_content, encoding="utf-8")

        # Second install without force
        r2 = execute_installation(target, force=False)
        assert r2.success is True
        assert len(r2.overwritten_files) == 0
        assert custom_file in r2.skipped_files

        # Ensure user content was preserved untouched
        assert custom_file.read_text(encoding="utf-8") == custom_content


def test_force_overwrites_modified_files():
    """Verify that --force replaces modified files with the packaged canonical versions."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "force_target"
        execute_installation(target, force=False)

        custom_file = target / "architecture-diagrams" / "SKILL.md"
        custom_content = "# User draft"
        custom_file.write_text(custom_content, encoding="utf-8")

        # Install with force=True
        r_force = execute_installation(target, force=True)
        assert r_force.success is True
        assert custom_file in r_force.overwritten_files
        assert custom_file.read_text(encoding="utf-8") == read_skill_content("architecture-diagrams")


def test_symlink_safety():
    """Verify that installer detects symlinks escaping the destination root and skips them."""
    with tempfile.TemporaryDirectory() as td:
        outside_dir = Path(td) / "outside_sandbox"
        outside_dir.mkdir()
        target = Path(td) / "safe_target"
        target.mkdir()

        # Create a malicious symlink pointing to an outside folder
        malicious_link = target / "architecture-diagrams"
        malicious_link.symlink_to(outside_dir, target_is_directory=True)

        _, plans = plan_installation(target, force=False)
        arch_plans = [p for p in plans if p.skill_name == "architecture-diagrams"]
        for p in arch_plans:
            assert p.action == InstallAction.SKIP
            assert "symlink" in p.reason.lower()


def test_permission_error_handling():
    """Verify graceful handling when destination cannot be written."""
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "readonly_target"
        target.mkdir()
        # Set read-only permissions
        target.chmod(stat.S_IREAD | stat.S_IEXEC)

        try:
            result = execute_installation(target, force=False)
            # Should either record errors or return success=False
            if result.errors:
                assert result.success is False
        finally:
            # Restore permissions for cleanup
            target.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)


def test_cli_exit_codes(capsys):
    """Verify CLI exit codes and behavior across various argument combinations."""
    # --list exit code 0
    assert run_install_skills_cli(["--list"]) == 0
    captured = capsys.readouterr()
    assert "Available Agent Skills" in captured.out
    assert "Total: 6 skills" in captured.out

    # Missing --target argument
    assert run_install_skills_cli([]) == 1
    captured_err = capsys.readouterr()
    assert "Error: --target directory is required" in captured_err.err

    # Invalid root path
    assert run_install_skills_cli(["--target", "/"]) == 1

    # Valid install with temp dir
    with tempfile.TemporaryDirectory() as td:
        t = str(Path(td) / "cli_target")
        assert run_install_skills_cli(["--target", t]) == 0
        assert (Path(t) / "architecture-diagrams" / "SKILL.md").exists()

        # Dry run with force
        assert run_install_skills_cli(["--target", t, "--force", "--dry-run"]) == 0
