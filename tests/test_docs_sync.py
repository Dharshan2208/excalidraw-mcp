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
        self.assertEqual(len(reg_full), 20)
