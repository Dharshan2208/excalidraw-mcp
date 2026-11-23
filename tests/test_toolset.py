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
    async def test_core_toolset_registers_curated_tools(self):
        server = create_server(toolset="core")
        tools = await server.list_tools()
        tool_names = {t.name for t in tools}

        self.assertEqual(len(tools), 12)
        # Verify essential core tools are present (Option B Core Roster)
        self.assertIn("create_shape", tool_names)
        self.assertIn("create_connector", tool_names)
        self.assertIn("add_frame", tool_names)
        self.assertIn("add_text", tool_names)
        self.assertIn("update_element", tool_names)
        self.assertIn("delete", tool_names)
        self.assertIn("clear", tool_names)
        self.assertIn("undo", tool_names)
        self.assertIn("batch_mutate", tool_names)
        self.assertIn("inspect_scene", tool_names)
        self.assertIn("auto_fix_layout", tool_names)
        self.assertIn("preview", tool_names)

        # Verify full-only tools are NOT in core
        self.assertNotIn("generate_diagram", tool_names)
        self.assertNotIn("scene_storage", tool_names)
        self.assertNotIn("export_png", tool_names)
        self.assertNotIn("export_svg", tool_names)
        self.assertNotIn("lock_elements", tool_names)
        self.assertNotIn("unlock_elements", tool_names)
        self.assertNotIn("group_elements", tool_names)
        self.assertNotIn("ungroup_elements", tool_names)
        self.assertNotIn("get_viewport", tool_names)
        self.assertNotIn("set_viewport", tool_names)
        self.assertNotIn("focus_elements", tool_names)
        self.assertNotIn("start_live_server", tool_names)
        self.assertNotIn("stop_live_server", tool_names)
        self.assertNotIn("live_server", tool_names)
        self.assertNotIn("manage_element_state", tool_names)
        self.assertNotIn("get_live_server_status", tool_names)

    async def test_full_toolset_registers_all_tools(self):
        server = create_server(toolset="full")
        tools = await server.list_tools()
        self.assertEqual(len(tools), 21)
        tool_names = {t.name for t in tools}
        self.assertIn("generate_diagram", tool_names)
        self.assertIn("scene_storage", tool_names)
        self.assertIn("export_png", tool_names)
        self.assertIn("export_svg", tool_names)
        self.assertIn("batch_mutate", tool_names)
        self.assertIn("inspect_scene", tool_names)
        self.assertIn("live_server", tool_names)
        self.assertIn("manage_element_state", tool_names)
        self.assertIn("read_diagram_guide", tool_names)
        self.assertNotIn("list_fonts", tool_names)
        self.assertNotIn("start_live_server", tool_names)
        self.assertNotIn("stop_live_server", tool_names)
        self.assertNotIn("set_element_locked", tool_names)
        self.assertNotIn("manage_groups", tool_names)
        self.assertNotIn("duplicate_elements", tool_names)
        self.assertNotIn("add_code_block", tool_names)
        self.assertNotIn("save", tool_names)
        self.assertNotIn("load", tool_names)
        self.assertNotIn("list_saved_scenes", tool_names)
        self.assertNotIn("export_scene", tool_names)
        self.assertNotIn("import_scene", tool_names)
        self.assertNotIn("draw_graph", tool_names)
        self.assertNotIn("draw_mermaid", tool_names)
        self.assertNotIn("draw_architecture", tool_names)
        self.assertNotIn("move", tool_names)
        self.assertNotIn("resize", tool_names)
        self.assertNotIn("get_scene", tool_names)
        self.assertNotIn("get_element", tool_names)
        self.assertNotIn("find_elements", tool_names)
        self.assertNotIn("get_resource", tool_names)
        self.assertNotIn("get_viewport", tool_names)
        self.assertNotIn("get_scene_summary", tool_names)
        self.assertNotIn("describe_scene", tool_names)
        self.assertNotIn("get_live_server_status", tool_names)

    async def test_batch_mutate_in_core_actionable_errors(self):
        server = create_server(toolset="core")
        async with Client(server) as client:
            res = await client.call_tool(
                "batch_mutate",
                {"operations": [{"action": "move", "element_id": "nonexistent", "x": 10, "y": 20}]},
                raise_on_error=False,
            )
            self.assertTrue(res.is_error)
            self.assertIn("Element 'nonexistent' not found", res.content[0].text)

    async def test_capabilities_resource_provides_metadata(self):
        for mode in ("core", "full"):
            server = create_server(toolset=mode)
            res = await server.read_resource("excalidraw://capabilities")
            self.assertTrue(len(res.contents) > 0)
            data = json.loads(res.contents[0].content)
            self.assertEqual(data["active_toolset"], mode)
            self.assertEqual(data["server_version"], "0.4.0")
            self.assertIn("capabilities", data)
            self.assertIn("full_only_features", data["capabilities"])
            self.assertEqual(data["tool_count"], 21 if mode == "full" else 12)
            self.assertNotIn("find_elements", data["capabilities"]["full_only_features"])
            self.assertNotIn("get_resource", data["capabilities"]["full_only_features"])

    def test_get_resource_supports_exca_mcp_skills_and_capabilities(self):
        from excalidraw_mcp.resources import get_resource
        from excalidraw_mcp.service import SceneService
        service = SceneService()

        # exca-mcp:// URI scheme for skills
        skill_res = get_resource(service, uri="exca-mcp://skills/diagram-planning")
        self.assertEqual(skill_res["resource_type"], "skill")
        self.assertEqual(skill_res["identifier"], "diagram-planning")
        self.assertIn("content", skill_res)

        # exca-mcp://skills/index
        index_res = get_resource(service, uri="exca-mcp://skills/index")
        self.assertEqual(index_res["resource_type"], "skill")
        self.assertIn("skills", index_res["index"])

        # excalidraw://capabilities resource via get_resource
        cap_res = get_resource(service, uri="excalidraw://capabilities")
        self.assertEqual(cap_res["server_version"], "0.4.0")
        self.assertIn(cap_res["tool_count"], (12, 21))

    async def test_documentation_and_font_resources(self):
        server = create_server(toolset="core")
        resources = await server.list_resources()
        resource_uris = {str(r.uri) for r in resources}
        self.assertIn("excalidraw://fonts", resource_uris)

        fonts_res = await server.read_resource("excalidraw://fonts")
        self.assertTrue(len(fonts_res.contents) > 0)
        fonts_data = json.loads(fonts_res.contents[0].content)
        self.assertIn("fonts", fonts_data)
        self.assertIn("total", fonts_data)

        guide_res = await server.read_resource("excalidraw://guide/layout")
        self.assertTrue(len(guide_res.contents) > 0)
        self.assertIn("# Diagram Layout & Flow Structure", guide_res.contents[0].content)
        self.assertIn("## Principles", guide_res.contents[0].content)


class Phase2ConsolidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_set_element_locked_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        rect = tools["create_shape"](type="rectangle", x=0, y=0, w=100, h=50, label="Box")
        rid = rect["rectangle_id"]

        # Lock via unified tool
        res1 = tools["manage_element_state"](element_ids=[rid], action="lock")
        self.assertEqual(res1["status"], "locked")

        # Unlock via unified tool
        res2 = tools["manage_element_state"](element_ids=[rid], action="unlock")
        self.assertEqual(res2["status"], "unlocked")

        # Verify legacy wrappers are removed from MCP tools
        self.assertNotIn("set_element_locked", tools)
        self.assertNotIn("lock_elements", tools)
        self.assertNotIn("unlock_elements", tools)

    async def test_manage_groups_and_wrappers(self):
        server = create_server(toolset="full")
        tools = {t.name: t.fn for t in await server.list_tools()}
        r1 = tools["create_shape"](type="rectangle", x=0, y=0, w=100, h=50, label="A")
        r2 = tools["create_shape"](type="rectangle", x=120, y=0, w=100, h=50, label="B")
        ids = [r1["rectangle_id"], r2["rectangle_id"]]

        # Group via unified tool
        res1 = tools["manage_element_state"](element_ids=ids, action="group")
        self.assertEqual(res1["status"], "grouped")
        gid = res1["group_id"]

        # Ungroup via unified tool
        res2 = tools["manage_element_state"](group_id=gid, action="ungroup")
        self.assertEqual(res2["status"], "ungrouped")

        # Verify legacy wrappers are removed from MCP tools
        self.assertNotIn("manage_groups", tools)
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
        el = tools["inspect_scene"](mode="element", element_id=rid)["element"]
        self.assertEqual(el["x"], 50)
        self.assertEqual(el["y"], 60)
        self.assertEqual(el["width"], 150)
        self.assertEqual(el["height"], 80)
        self.assertNotIn("move", tools)
        self.assertNotIn("resize", tools)


if __name__ == "__main__":
    unittest.main()
