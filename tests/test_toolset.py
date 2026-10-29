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
    async def test_core_toolset_registers_exactly_25_tools(self):
        server = create_server(toolset="core")
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}

        self.assertEqual(len(tools), 25)
        # Verify essential core tools are present
        self.assertIn("add_rectangle", tool_names)
        self.assertIn("add_circle", tool_names)
        self.assertIn("add_diamond", tool_names)
        self.assertIn("add_arrow", tool_names)
        self.assertIn("connect", tool_names)
        self.assertIn("add_frame", tool_names)
        self.assertIn("add_text", tool_names)
        self.assertIn("move", tool_names)
        self.assertIn("resize", tool_names)
        self.assertIn("update_element", tool_names)
        self.assertIn("delete", tool_names)
        self.assertIn("clear", tool_names)
        self.assertIn("undo", tool_names)
        self.assertIn("get_scene", tool_names)
        self.assertIn("get_element", tool_names)
        self.assertIn("get_scene_summary", tool_names)
        self.assertIn("describe_scene", tool_names)
        self.assertIn("auto_fix_layout", tool_names)
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
        self.assertNotIn("find_elements", tool_names)
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
        self.assertNotIn("get_canvas_screenshot", tool_names)

    async def test_full_toolset_registers_all_tools(self):
        server = create_server(toolset="full")
        tools = await server.list_tools()
        self.assertEqual(len(tools), 49)
        tool_names = {t.name for t in tools}
        self.assertIn("draw_graph", tool_names)
        self.assertIn("batch_mutate", tool_names)
        self.assertIn("find_elements", tool_names)
        self.assertIn("start_live_server", tool_names)
        self.assertIn("get_canvas_screenshot", tool_names)
        self.assertIn("set_element_locked", tool_names)
        self.assertIn("manage_groups", tool_names)

    async def test_get_canvas_screenshot_emits_deprecation_warning(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        self.assertIn("get_canvas_screenshot", tools)

        with warnings.catch_warnings(record=True) as recorded:
            warnings.simplefilter("always")
            tools["get_canvas_screenshot"]()
            self.assertTrue(
                any(
                    issubclass(w.category, DeprecationWarning)
                    and "get_canvas_screenshot is deprecated; use preview instead." in str(w.message)
                    for w in recorded
                )
            )

    async def test_capabilities_resource_provides_metadata(self):
        for mode in ("core", "full"):
            server = create_server(toolset=mode)
            res = await server.read_resource("excalidraw://capabilities")
            self.assertTrue(len(res.contents) > 0)
            data = json.loads(res.contents[0].content)
            self.assertEqual(data["active_toolset"], mode)
            self.assertIn("capabilities", data)
            self.assertIn("full_only_features", data["capabilities"])
            self.assertEqual(data["tool_count"], 46 if mode == "full" else 25)


class Phase2ConsolidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_element_locked_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        rect = tools["add_rectangle"](x=0, y=0, w=100, h=50, label="Box")
        rid = rect["rectangle_id"]

        # Lock via unified tool
        res1 = tools["set_element_locked"](element_ids=[rid], locked=True)
        self.assertEqual(res1["status"], "locked")

        # Unlock via unified tool
        res2 = tools["set_element_locked"](element_ids=[rid], locked=False)
        self.assertEqual(res2["status"], "unlocked")

        # Lock via legacy wrapper
        res3 = tools["lock_elements"](element_ids=[rid])
        self.assertEqual(res3["status"], "locked")

        # Unlock via legacy wrapper
        res4 = tools["unlock_elements"](element_ids=[rid])
        self.assertEqual(res4["status"], "unlocked")

    async def test_manage_groups_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        r1 = tools["add_rectangle"](x=0, y=0, w=100, h=50, label="A")
        r2 = tools["add_rectangle"](x=120, y=0, w=100, h=50, label="B")
        ids = [r1["rectangle_id"], r2["rectangle_id"]]

        # Group via unified tool
        res1 = tools["manage_groups"](element_ids=ids, action="group")
        self.assertEqual(res1["status"], "grouped")
        gid = res1["group_id"]

        # Ungroup via unified tool
        res2 = tools["manage_groups"](group_id=gid, action="ungroup")
        self.assertEqual(res2["status"], "ungrouped")

        # Group and ungroup via legacy wrappers
        res3 = tools["group_elements"](element_ids=ids)
        self.assertEqual(res3["status"], "grouped")
        res4 = tools["ungroup_elements"](group_id=res3["group_id"])
        self.assertEqual(res4["status"], "ungrouped")

    async def test_set_viewport_with_focus_elements(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        r1 = tools["add_rectangle"](x=50, y=50, w=100, h=50, label="A")
        r2 = tools["add_rectangle"](x=200, y=100, w=100, h=50, label="B")
        ids = [r1["rectangle_id"], r2["rectangle_id"]]

        # Set viewport with focus_element_ids
        res = tools["set_viewport"](focus_element_ids=ids, padding=40)
        self.assertEqual(res["status"], "focused")
        self.assertIn("bounding_box", res)

        # Legacy focus_elements wrapper
        res2 = tools["focus_elements"](element_ids=ids, padding=40)
        self.assertEqual(res2["status"], "focused")
        self.assertIn("bounding_box", res2)


if __name__ == "__main__":
    unittest.main()
