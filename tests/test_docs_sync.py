"""Verification test ensuring documentation remains in sync with real server tools."""

import asyncio
from pathlib import Path
import re
import unittest

from excalidraw_mcp.server import create_server


class DocumentationSyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_tools_md_matches_registered_tools(self):
        repo_root = Path(__file__).resolve().parent.parent
        tools_md = repo_root / "docs" / "tools.md"
        self.assertTrue(tools_md.exists(), f"Missing documentation file: {tools_md}")

        content = tools_md.read_text(encoding="utf-8")
        core_section = content.split("## 2. Full Profile Tools")[0]
        full_section = content.split("## 2. Full Profile Tools")[1].split("## 3. MCP Resources")[0]

        doc_core = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|\s*\*\*CORE\*\*", core_section, re.MULTILINE))
        doc_full_only = set(re.findall(r"^\|\s*`([a-z_]+)`\s*\|\s*FULL", full_section, re.MULTILINE))
        doc_all = doc_core | doc_full_only

        # Check core profile registration
        core_server = create_server(toolset="core")
        reg_core = {t.name for t in await core_server.list_tools()}
        self.assertEqual(
            doc_core,
            reg_core,
            f"Core tool mismatch between docs/tools.md and server: {doc_core ^ reg_core}",
        )
        self.assertEqual(len(reg_core), 12)

        # Check full profile registration
        full_server = create_server(toolset="full")
        reg_full = {t.name for t in await full_server.list_tools()}
        self.assertEqual(
            doc_all,
            reg_full,
            f"Full tool mismatch between docs/tools.md and server: {doc_all ^ reg_full}",
        )
        self.assertEqual(len(reg_full), 21)

    def test_package_version_and_security_policy_sync(self):
        """Verify __version__, pyproject.toml, SECURITY.md, and docs/tools.md are synchronized (M-029, M-030)."""
        import excalidraw_mcp

        repo_root = Path(__file__).resolve().parent.parent

        # 1. __version__ == pyproject.toml version
        pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        version_match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        self.assertIsNotNone(version_match, "Could not find version in pyproject.toml")
        expected_version = version_match.group(1)
        self.assertEqual(excalidraw_mcp.__version__, expected_version)
        self.assertEqual(excalidraw_mcp.__version__, "0.4.0")

        # 2. SECURITY.md includes current major.minor
        security_md = (repo_root / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("0.4.x", security_md)

        # 3. docs/tools.md parameter names match implementation
        tools_md = (repo_root / "docs" / "tools.md").read_text(encoding="utf-8")
        self.assertIn('format: "mermaid"', tools_md)
        self.assertIn("verbose: bool = False", tools_md)
        self.assertIn('"share_url"', tools_md)
        self.assertIn("readability", tools_md)

    def test_release_workflow_attaches_distribution_assets(self):
        """Verify release workflow includes GitHub release creation with wheel/sdist assets (P-006)."""
        repo_root = Path(__file__).resolve().parent.parent
        release_yml = (repo_root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("softprops/action-gh-release@v2", release_yml)
        self.assertIn("contents: write", release_yml)
        self.assertIn("files: dist/*", release_yml)
