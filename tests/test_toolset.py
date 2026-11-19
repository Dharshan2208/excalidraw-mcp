"""Tests for EXCALIDRAW_TOOLSET=core|full configuration and toolset rationalization."""

import asyncio
import json
import os
import unittest
import warnings
from unittest.mock import patch

from excalidraw_mcp.config import configured_toolset
from excalidraw_mcp.server import create_server
from fastmcp import Client


class ToolsetConfigurationTests(unittest.TestCase):
    def test_configured_toolset_default_is_core(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(configured_toolset(), "core")

    def test_configured_toolset_respects_full(self):
        with patch.dict(os.environ, {"EXCALIDRAW_TOOLSET": "full"}):
            self.assertEqual(configured_toolset(), "full")

    def test_configured_toolset_normalizes_case_and_whitespace(self):
        with patch.dict(os.environ, {"EXCALIDRAW_TOOLSET": "  FULL  "}):
            self.assertEqual(configured_toolset(), "full")
        with patch.dict(os.environ, {"EXCALIDRAW_TOOLSET": "CORE"}):
            self.assertEqual(configured_toolset(), "core")

    def test_configured_toolset_fallback_on_invalid_value(self):
        with patch.dict(os.environ, {"EXCALIDRAW_TOOLSET": "everything"}):
            self.assertEqual(configured_toolset(), "core")


class ToolsetRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_core_toolset_registers_exactly_22_tools(self):
        server = create_server(toolset="core")
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}

        self.assertEqual(len(tools), 22)
        # Verify essential core tools are present
        self.assertIn("create_shape", tool_names)
        self.assertIn("create_connector", tool_names)
        self.assertIn("add_frame", tool_names)
        self.assertIn("add_text", tool_names)
        self.assertIn("update_element", tool_names)
        self.assertIn("delete", tool_names)
        self.assertIn("clear", tool_names)
        self.assertIn("undo", tool_names)
        self.assertIn("get_scene", tool_names)
        self.assertIn("get_element", tool_names)
        self.assertIn("get_scene_summary", tool_names)
        self.assertIn("describe_scene", tool_names)
        self.assertIn("auto_fix_layout", tool_names)
        self.assertIn("find_elements", tool_names)
        self.assertIn("get_resource", tool_names)
        self.assertIn("draw_mermaid", tool_names)
        self.assertIn("draw_architecture", tool_names)
        self.assertIn("save", tool_names)
        self.assertIn("load", tool_names)
        self.assertIn("preview", tool_names)
        self.assertIn("export_png", tool_names)
        self.assertIn("export_scene", tool_names)

        # Verify full-only tools are NOT in core
        self.assertNotIn("draw_graph", tool_names)
        self.assertNotIn("batch_mutate", tool_names)
        self.assertNotIn("lock_elements", tool_names)
        self.assertNotIn("unlock_elements", tool_names)
        self.assertNotIn("group_elements", tool_names)
        self.assertNotIn("ungroup_elements", tool_names)
        self.assertNotIn("get_viewport", tool_names)
        self.assertNotIn("set_viewport", tool_names)
        self.assertNotIn("focus_elements", tool_names)
        self.assertNotIn("start_live_server", tool_names)
        self.assertNotIn("stop_live_server", tool_names)
        self.assertNotIn("get_live_server_status", tool_names)

    async def test_full_toolset_registers_all_tools(self):
        server = create_server(toolset="full")
        tools = await server.list_tools()
        self.assertEqual(len(tools), 38)
        tool_names = {t.name for t in tools}
        self.assertIn("draw_graph", tool_names)
        self.assertIn("batch_mutate", tool_names)
        self.assertIn("find_elements", tool_names)
        self.assertIn("start_live_server", tool_names)
        self.assertIn("set_element_locked", tool_names)
        self.assertIn("manage_groups", tool_names)
        self.assertNotIn("move", tool_names)
        self.assertNotIn("resize", tool_names)
        self.assertNotIn("lock_elements", tool_names)
        self.assertNotIn("unlock_elements", tool_names)
        self.assertNotIn("group_elements", tool_names)
        self.assertNotIn("ungroup_elements", tool_names)
        self.assertNotIn("focus_elements", tool_names)

    async def test_capabilities_resource_provides_metadata(self):
        for mode in ("core", "full"):
            server = create_server(toolset=mode)
            res = await server.read_resource("excalidraw://capabilities")
            self.assertTrue(len(res.contents) > 0)
            data = json.loads(res.contents[0].content)
            self.assertEqual(data["active_toolset"], mode)
            self.assertEqual(data["server_version"], "0.2.0")
            self.assertIn("capabilities", data)
            self.assertIn("full_only_features", data["capabilities"])
            self.assertEqual(data["tool_count"], 38 if mode == "full" else 22)
            self.assertNotIn("find_elements", data["capabilities"]["full_only_features"])
            self.assertNotIn("get_resource", data["capabilities"]["full_only_features"])


class Phase2ConsolidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_element_locked_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        rect = tools["create_shape"](type="rectangle", x=0, y=0, w=100, h=50, label="Box")
        rid = rect["rectangle_id"]

        # Lock via unified tool
        res1 = tools["set_element_locked"](element_ids=[rid], locked=True)
        self.assertEqual(res1["status"], "locked")

        # Unlock via unified tool
        res2 = tools["set_element_locked"](element_ids=[rid], locked=False)
        self.assertEqual(res2["status"], "unlocked")

        # Verify legacy wrappers are removed from MCP tools
        self.assertNotIn("lock_elements", tools)
        self.assertNotIn("unlock_elements", tools)

    async def test_manage_groups_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        r1 = tools["create_shape"](type="rectangle", x=0, y=0, w=100, h=50, label="A")
        r2 = tools["create_shape"](type="rectangle", x=120, y=0, w=100, h=50, label="B")
        ids = [r1["rectangle_id"], r2["rectangle_id"]]

        # Group via unified tool
        res1 = tools["manage_groups"](element_ids=ids, action="group")
        self.assertEqual(res1["status"], "grouped")
        gid = res1["group_id"]

        # Ungroup via unified tool
        res2 = tools["manage_groups"](group_id=gid, action="ungroup")
        self.assertEqual(res2["status"], "ungrouped")

        # Verify legacy wrappers are removed from MCP tools
        self.assertNotIn("group_elements", tools)
        self.assertNotIn("ungroup_elements", tools)

    async def test_set_viewport_with_focus_elements(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        r1 = tools["create_shape"](type="rectangle", x=50, y=50, w=100, h=50, label="A")
        r2 = tools["create_shape"](type="rectangle", x=200, y=100, w=100, h=50, label="B")
        ids = [r1["rectangle_id"], r2["rectangle_id"]]

        # Set viewport with focus_element_ids
        res = tools["set_viewport"](focus_element_ids=ids, padding=40)
        self.assertEqual(res["status"], "focused")
        self.assertIn("bounding_box", res)

        # Verify legacy wrapper is removed from MCP tools
        self.assertNotIn("focus_elements", tools)

    async def test_update_element_absorbs_move_and_resize(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        rect = tools["create_shape"](type="rectangle", x=10, y=20, w=100, h=50, label="Original")
        rid = rect["rectangle_id"]

        # Move and resize via update_element
        res = tools["update_element"](element_id=rid, x=50, y=60, width=150, height=80, label="Updated")
        self.assertEqual(res["element_id"], rid)
        el = tools["get_element"](element_id=rid)["element"]
        self.assertEqual(el["x"], 50)
        self.assertEqual(el["y"], 60)
        self.assertEqual(el["width"], 150)
        self.assertEqual(el["height"], 80)
        self.assertNotIn("move", tools)
        self.assertNotIn("resize", tools)


if __name__ == "__main__":
    unittest.main()
