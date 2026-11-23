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
    get_claude_skill_dir,
    plan_claude_installation,
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
            target = Path(td).resolve() / "custom_target"
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
            target = Path(td).resolve() / "force_target"
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

    def test_symlink_sibling_prefix_safety(self):
        """Verify that symlinks to a sibling directory starting with identical string prefix are rejected (M-027)."""
        with tempfile.TemporaryDirectory() as td:
            # Sibling directory starts with same prefix "safe_target"
            sibling_escaped = Path(td) / "safe_target-escaped"
            sibling_escaped.mkdir()
            target = Path(td) / "safe_target"
            target.mkdir()

            # Point skill to sibling that would fool a simple string startswith check
            malicious_link = target / "architecture-diagrams"
            malicious_link.symlink_to(sibling_escaped, target_is_directory=True)

            _, plans = plan_installation(target, force=False)
            arch_plans = [p for p in plans if p.skill_name == "architecture-diagrams"]
            for p in arch_plans:
                self.assertEqual(p.action, InstallAction.SKIP)
                self.assertIn("escaping", p.reason.lower())

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

    def test_claude_skill_installation_defaults_and_structure(self):
        """Verify Claude Code skill packaging under ~/.claude/skills/excalidraw/ with frontmatter and references (M-006)."""
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td) / "fake_home"
            fake_home.mkdir()

            with patch("pathlib.Path.home", return_value=fake_home), patch.dict(os.environ, {}, clear=True):
                # 1. Default directory resolution
                expected_dir = fake_home / ".claude" / "skills"
                self.assertEqual(get_claude_skill_dir(), expected_dir)

                # 2. Plan installation
                root, plans = plan_claude_installation()
                self.assertEqual(root, expected_dir.resolve())
                skill_file_plan = next(p for p in plans if p.rel_path == "SKILL.md")
                self.assertEqual(skill_file_plan.dest_path, expected_dir.resolve() / "excalidraw" / "SKILL.md")
                # Frontmatter checks
                self.assertIn("name: excalidraw", skill_file_plan.content)
                self.assertIn("description:", skill_file_plan.content)
                self.assertIn("## Role", skill_file_plan.content)

                # 3. Dry run
                res_dry = execute_installation(force=False, dry_run=True, is_claude=True)
                self.assertTrue(res_dry.success)
                self.assertFalse((expected_dir / "excalidraw").exists())

                # 4. Real installation
                res_real = execute_installation(force=False, dry_run=False, is_claude=True)
                self.assertTrue(res_real.success)
                installed_skill = expected_dir / "excalidraw" / "SKILL.md"
                self.assertTrue(installed_skill.is_file())
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), skill_file_plan.content)

                # Reference files present
                self.assertTrue((expected_dir / "excalidraw" / "references" / "architecture-patterns.md").is_file())
                self.assertTrue((expected_dir / "excalidraw" / "references" / "palette-catalog.md").is_file())
                # Discovery links in SKILL.md (P-010)
                skill_text = installed_skill.read_text(encoding="utf-8")
                self.assertIn("references/architecture-patterns.md", skill_text)
                self.assertIn("references/palette-catalog.md", skill_text)
                self.assertIn("Bundled Reference Guidelines", skill_text)

                # 5. Idempotent second run
                res_idempotent = execute_installation(force=False, dry_run=False, is_claude=True)
                self.assertTrue(res_idempotent.success)
                self.assertEqual(len(res_idempotent.installed_files), 0)
                self.assertGreater(len(res_idempotent.skipped_files), 0)

    def test_claude_skill_cli_overrides_and_safety(self):
        """Verify Claude Code CLI subcommand arguments, CLAUDE_CONFIG_DIR, and overwrite safety (M-006)."""
        with tempfile.TemporaryDirectory() as td:
            fake_config_dir = Path(td) / "custom_claude_config"
            fake_config_dir.mkdir()

            # Test CLAUDE_CONFIG_DIR environment variable override
            with patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(fake_config_dir)}):
                self.assertEqual(get_claude_skill_dir(), fake_config_dir / "skills")

                # Install via CLI using --claude
                exit_code = run_install_skills_cli(["--claude"])
                self.assertEqual(exit_code, 0)
                installed_skill = fake_config_dir / "skills" / "excalidraw" / "SKILL.md"
                self.assertTrue(installed_skill.is_file())

                # User modifies skill file
                custom_content = "# User custom modification\n"
                installed_skill.write_text(custom_content, encoding="utf-8")

                # Install again without --force -> user content is preserved
                exit_code = run_install_skills_cli(["--claude"])
                self.assertEqual(exit_code, 0)
                self.assertEqual(installed_skill.read_text(encoding="utf-8"), custom_content)

                # Install again with --force -> canonical content restored
                exit_code = run_install_skills_cli(["--claude", "--force"])
                self.assertEqual(exit_code, 0)
                self.assertNotEqual(installed_skill.read_text(encoding="utf-8"), custom_content)
                self.assertIn("name: excalidraw", installed_skill.read_text(encoding="utf-8"))

            # Test explicit --dir override with --claude
            custom_dir = Path(td) / "project_local_skills"
            exit_code = run_install_skills_cli(["--claude", "--dir", str(custom_dir)])
            self.assertEqual(exit_code, 0)
            self.assertTrue((custom_dir / "excalidraw" / "SKILL.md").is_file())

    def test_cursor_and_windsurf_cli_shortcuts(self):
        """Verify --cursor and --windsurf shortcut targets install into .cursor/skills and .windsurf/skills (P-015)."""
        with tempfile.TemporaryDirectory() as td:
            orig_cwd = os.getcwd()
            try:
                os.chdir(td)
                # 1. Cursor shortcut
                cursor_exit = run_install_skills_cli(["--cursor"])
                self.assertEqual(cursor_exit, 0)
                cursor_skill = Path(td) / ".cursor" / "skills" / "architecture-diagrams" / "SKILL.md"
                self.assertTrue(cursor_skill.is_file())

                # 2. Windsurf shortcut
                windsurf_exit = run_install_skills_cli(["--windsurf"])
                self.assertEqual(windsurf_exit, 0)
                windsurf_skill = Path(td) / ".windsurf" / "skills" / "diagram-planning" / "SKILL.md"
                self.assertTrue(windsurf_skill.is_file())
            finally:
                os.chdir(orig_cwd)


if __name__ == "__main__":
    unittest.main()
