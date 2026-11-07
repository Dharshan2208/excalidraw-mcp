"""Tests for agent skills packaging, runtime resource loading, and discovery."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from excalidraw_mcp.skills import (
    InvalidSkillNameError,
    ReferenceNotFoundError,
    SkillNotFoundError,
    get_all_skills,
    get_skill_metadata,
    get_skills_index,
    get_skills_root,
    iter_skill_files,
    list_skill_references,
    list_skills,
    load_skill,
    read_reference_content,
    read_skill_content,
)

EXPECTED_SKILLS = [
    "architecture-diagrams",
    "diagram-planning",
    "excalidraw-workflow",
    "flowcharts-and-processes",
    "human-style-and-polish",
    "verify-and-editable-handoff",
]

EXPECTED_REFERENCES = {
    "architecture-diagrams": ["architecture-patterns"],
    "diagram-planning": ["entry-tool-decision-tree"],
    "excalidraw-workflow": [],
    "flowcharts-and-processes": ["flowchart-patterns"],
    "human-style-and-polish": ["anti-patterns", "palette-catalog"],
    "verify-and-editable-handoff": ["delivery-checklist"],
}


class SkillsDistributionTests(unittest.TestCase):
    def test_list_skills(self):
        """Verify all six skills are discoverable."""
        skills = list_skills()
        self.assertEqual(skills, sorted(EXPECTED_SKILLS))
        self.assertEqual(len(skills), 6)

    def test_load_all_skills(self):
        """Verify each skill can be loaded with valid metadata and content."""
        all_skills = get_all_skills()
        self.assertEqual(len(all_skills), 6)

        for name in EXPECTED_SKILLS:
            self.assertIn(name, all_skills)
            skill = all_skills[name]
            self.assertEqual(skill.name, name)
            self.assertGreater(len(skill.description), 10)
            self.assertGreater(len(skill.content), 100)
            self.assertTrue("name: " in skill.content or skill.content.startswith("#"))

            # Check references match expected list
            expected_refs = sorted(EXPECTED_REFERENCES[name])
            self.assertEqual(sorted(skill.reference_names), expected_refs)
            for ref_name in expected_refs:
                self.assertIn(ref_name, skill.references)
                self.assertGreater(len(skill.references[ref_name]), 50)

    def test_get_skill_metadata(self):
        """Verify metadata extraction for each skill."""
        for name in EXPECTED_SKILLS:
            meta = get_skill_metadata(name)
            self.assertEqual(meta.name, name)
            self.assertGreater(len(meta.description), 0)
            self.assertTrue(meta.has_skill_file)
            self.assertEqual(sorted(meta.reference_names), sorted(EXPECTED_REFERENCES[name]))

    def test_read_reference_content(self):
        """Verify reading individual reference documents with and without .md extension."""
        for skill_name, refs in EXPECTED_REFERENCES.items():
            for ref in refs:
                content_no_ext = read_reference_content(skill_name, ref)
                content_with_ext = read_reference_content(skill_name, f"{ref}.md")
                self.assertEqual(content_no_ext, content_with_ext)
                self.assertGreater(len(content_no_ext), 50)

    def test_unknown_skill_errors(self):
        """Verify appropriate error types for nonexistent skills."""
        with self.assertRaises(SkillNotFoundError):
            load_skill("nonexistent-skill-xyz")

        with self.assertRaises(SkillNotFoundError):
            read_skill_content("nonexistent-skill-xyz")

        with self.assertRaises(SkillNotFoundError):
            list_skill_references("nonexistent-skill-xyz")

    def test_unknown_reference_errors(self):
        """Verify appropriate error types for nonexistent references."""
        with self.assertRaises(ReferenceNotFoundError):
            read_reference_content("architecture-diagrams", "nonexistent-reference-doc")

        # Skill with no references directory
        with self.assertRaises(ReferenceNotFoundError):
            read_reference_content("excalidraw-workflow", "any-ref")

    def test_path_traversal_prevention(self):
        """Verify path traversal attempts are rejected."""
        traversal_attacks = [
            "../something",
            "../../etc/passwd",
            "/etc/passwd",
            "foo/bar",
            "foo\\bar",
            "skill\x00name",
            "",
            " ",
        ]
        for attack in traversal_attacks:
            with self.assertRaises(InvalidSkillNameError):
                load_skill(attack)

            with self.assertRaises(InvalidSkillNameError):
                read_reference_content("architecture-diagrams", attack)

    def test_iter_skill_files(self):
        """Verify file iteration preserves relative hierarchy."""
        for name in EXPECTED_SKILLS:
            files = iter_skill_files(name)
            rel_paths = [f[0] for f in files]

            self.assertIn("SKILL.md", rel_paths)
            expected_refs = EXPECTED_REFERENCES[name]
            for ref in expected_refs:
                self.assertIn(f"references/{ref}.md", rel_paths)

    def test_skills_index(self):
        """Verify discovery index structure and URI format."""
        idx = get_skills_index()
        self.assertEqual(idx["total_skills"], 6)
        self.assertEqual(len(idx["skills"]), 6)
        self.assertIn("recommended_workflow", idx)

        skill_map = {s["name"]: s for s in idx["skills"]}
        for name in EXPECTED_SKILLS:
            entry = skill_map[name]
            self.assertEqual(entry["resource_uri"], f"exca-mcp://skills/{name}")
            ref_names = [r["name"] for r in entry["references"]]
            self.assertEqual(sorted(ref_names), sorted(EXPECTED_REFERENCES[name]))
            for r in entry["references"]:
                self.assertEqual(r["resource_uri"], f"exca-mcp://skills/{name}/references/{r['name']}")

    def test_wheel_archive_contents(self):
        """Verify that uv build produces a wheel containing all skills and references."""
        subprocess.run(["uv", "build"], check=True, capture_output=True)
        dist_dir = Path("dist")
        wheels = list(dist_dir.glob("*.whl"))
        self.assertGreater(len(wheels), 0)
        wheel_path = sorted(wheels, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        with zipfile.ZipFile(wheel_path) as zf:
            namelist = zf.namelist()

            for name in EXPECTED_SKILLS:
                expected_skill_path = f"excalidraw_mcp/skills/{name}/SKILL.md"
                self.assertIn(expected_skill_path, namelist, f"Missing {expected_skill_path} in wheel")

                for ref in EXPECTED_REFERENCES[name]:
                    expected_ref_path = f"excalidraw_mcp/skills/{name}/references/{ref}.md"
                    self.assertIn(expected_ref_path, namelist, f"Missing {expected_ref_path} in wheel")

    def test_sdist_archive_contents(self):
        """Verify that source distribution contains all skills and references."""
        dist_dir = Path("dist")
        sdists = list(dist_dir.glob("*.tar.gz"))
        self.assertGreater(len(sdists), 0)
        sdist_path = sorted(sdists, key=lambda p: p.stat().st_mtime, reverse=True)[0]

        with tarfile.open(sdist_path, "r:gz") as tf:
            names = tf.getnames()

            for name in EXPECTED_SKILLS:
                skill_found = any(n.endswith(f".skills/{name}/SKILL.md") for n in names)
                self.assertTrue(skill_found, f"Missing {name}/SKILL.md in sdist")

                for ref in EXPECTED_REFERENCES[name]:
                    ref_found = any(
                        n.endswith(f".skills/{name}/references/{ref}.md") for n in names
                    )
                    self.assertTrue(ref_found, f"Missing {name}/references/{ref}.md in sdist")

    def test_installed_package_resource_loading(self):
        """Verify that in an isolated installation from the wheel, skills load via importlib.resources."""
        dist_dir = Path("dist")
        wheels = list(dist_dir.glob("*.whl"))
        self.assertGreater(len(wheels), 0)
        wheel_path = sorted(wheels, key=lambda p: p.stat().st_mtime, reverse=True)[0].resolve()

        with tempfile.TemporaryDirectory() as td:
            venv_path = Path(td) / "clean_venv"
            subprocess.run(["uv", "venv", str(venv_path)], check=True, capture_output=True)
            py_bin = venv_path / "bin" / "python"

            subprocess.run(
                ["uv", "pip", "install", "--python", str(py_bin), str(wheel_path)],
                check=True,
                capture_output=True,
            )

            script = """
from excalidraw_mcp.skills import list_skills, get_all_skills, get_skills_root
root = get_skills_root()
skills = list_skills()
assert len(skills) == 6, f"Expected 6 skills, got {len(skills)}: {skills}"
all_skills = get_all_skills()
assert len(all_skills) == 6
for name, s in all_skills.items():
    assert len(s.content) > 100
    for ref_name, ref_content in s.references.items():
        assert len(ref_content) > 50
print("INSTALLED_LOADER_SUCCESS")
"""
            proc = subprocess.run(
                [str(py_bin), "-c", script],
                cwd=td,
                capture_output=True,
                text=True,
            )
            self.assertEqual(proc.returncode, 0, f"Script failed with stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}")
            self.assertIn("INSTALLED_LOADER_SUCCESS", proc.stdout)


if __name__ == "__main__":
    unittest.main()
