"""Tests for CLI agent skills installer."""

from __future__ import annotations

import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class SkillsInstallerTests(unittest.TestCase):
    def test_validate_target_dir(self):
        """Verify target directory validation, expansion, and security checks."""
        # Home expansion
        home_path = validate_target_dir("~/.skills")
        self.assertTrue(str(home_path).startswith(str(Path.home())))

        # Empty target raises ValueError
        with self.assertRaises(ValueError):
            validate_target_dir("")

        with self.assertRaises(ValueError):
            validate_target_dir("   ")

        # Root target is forbidden
        with self.assertRaises(ValueError):
            validate_target_dir("/")

    def test_install_to_nonexistent_directory(self):
        """Verify installation creates all 6 skills and 6 references in a fresh directory."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "new_skills"
            self.assertFalse(target.exists())

            result = execute_installation(target, force=False, dry_run=False)
            self.assertTrue(result.success)
            self.assertEqual(len(result.errors), 0)

            # 6 SKILL.md files + 6 reference files = 12 total files
            self.assertEqual(len(result.installed_files), 12)
            self.assertEqual(len(result.skipped_files), 0)
            self.assertEqual(len(result.overwritten_files), 0)

            # Verify all 6 skills exist
            for skill_name in EXPECTED_SKILLS:
                skill_md = target / skill_name / "SKILL.md"
                self.assertTrue(skill_md.is_file(), f"Missing {skill_md}")
                self.assertEqual(skill_md.read_text(encoding="utf-8"), read_skill_content(skill_name))

                for ref in EXPECTED_REFERENCES[skill_name]:
                    ref_md = target / skill_name / "references" / f"{ref}.md"
                    self.assertTrue(ref_md.is_file(), f"Missing {ref_md}")
                    self.assertEqual(
                        ref_md.read_text(encoding="utf-8"),
                        read_reference_content(skill_name, ref),
                    )

    def test_dry_run_makes_no_filesystem_changes(self):
        """Verify that --dry-run previews actions without creating directories or files."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "dry_run_target"
            self.assertFalse(target.exists())

            result = execute_installation(target, force=False, dry_run=True)
            self.assertTrue(result.success)
            self.assertTrue(result.dry_run)
            self.assertEqual(len(result.installed_files), 12)

            # Crucial check: target directory must NOT be created
            self.assertFalse(target.exists())

    def test_repeated_installation_skips_identical_content(self):
        """Verify idempotency: re-running installation skips identical files without modifying them."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "idempotent_target"

            # First install
            r1 = execute_installation(target, force=False)
            self.assertTrue(r1.success)
            self.assertEqual(len(r1.installed_files), 12)

            # Second install (idempotent run)
            r2 = execute_installation(target, force=False)
            self.assertTrue(r2.success)
            self.assertEqual(len(r2.installed_files), 0)
            self.assertEqual(len(r2.skipped_files), 12)
            self.assertEqual(len(r2.overwritten_files), 0)

    def test_skip_modified_user_files_without_force(self):
        """Verify safety: existing modified files are preserved and never overwritten without --force."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "custom_target"
            execute_installation(target, force=False)

            custom_file = target / "architecture-diagrams" / "SKILL.md"
            custom_content = "# My Custom User Architect Skill\nDo not overwrite!"
            custom_file.write_text(custom_content, encoding="utf-8")

            # Second install without force
            r2 = execute_installation(target, force=False)
            self.assertTrue(r2.success)
            self.assertEqual(len(r2.overwritten_files), 0)
            self.assertIn(custom_file, r2.skipped_files)

            # Ensure user content was preserved untouched
            self.assertEqual(custom_file.read_text(encoding="utf-8"), custom_content)

    def test_force_overwrites_modified_files(self):
        """Verify that --force replaces modified files with the packaged canonical versions."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "force_target"
            execute_installation(target, force=False)

            custom_file = target / "architecture-diagrams" / "SKILL.md"
            custom_content = "# User draft"
            custom_file.write_text(custom_content, encoding="utf-8")

            # Install with force=True
            r_force = execute_installation(target, force=True)
            self.assertTrue(r_force.success)
            self.assertIn(custom_file, r_force.overwritten_files)
            self.assertEqual(
                custom_file.read_text(encoding="utf-8"),
                read_skill_content("architecture-diagrams"),
            )

    def test_symlink_safety(self):
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
                self.assertEqual(p.action, InstallAction.SKIP)
                self.assertIn("symlink", p.reason.lower())

    def test_permission_error_handling(self):
        """Verify graceful handling when destination cannot be written."""
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "readonly_target"
            target.mkdir()
            target.chmod(stat.S_IREAD | stat.S_IEXEC)

            try:
                result = execute_installation(target, force=False)
                if result.errors:
                    self.assertFalse(result.success)
            finally:
                target.chmod(stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)

    def test_cli_exit_codes(self):
        """Verify CLI exit codes and behavior across various argument combinations."""
        # --list exit code 0
        with patch("sys.stdout", new=io.StringIO()) as fake_out:
            self.assertEqual(run_install_skills_cli(["--list"]), 0)
            out = fake_out.getvalue()
            self.assertIn("Available Agent Skills", out)
            self.assertIn("Total: 6 skills", out)

        # Missing --target argument
        with patch("sys.stderr", new=io.StringIO()) as fake_err:
            self.assertEqual(run_install_skills_cli([]), 1)
            err = fake_err.getvalue()
            self.assertIn("Error: --target directory is required", err)

        # Invalid root path
        with patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(run_install_skills_cli(["--target", "/"]), 1)

        # Valid install with temp dir
        with tempfile.TemporaryDirectory() as td:
            t = str(Path(td) / "cli_target")
            self.assertEqual(run_install_skills_cli(["--target", t]), 0)
            self.assertTrue((Path(t) / "architecture-diagrams" / "SKILL.md").exists())

            # Dry run with force
            self.assertEqual(run_install_skills_cli(["--target", t, "--force", "--dry-run"]), 0)


if __name__ == "__main__":
    unittest.main()
