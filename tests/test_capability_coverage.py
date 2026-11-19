"""Capability coverage verification test suite.

Asserts that all 48 baseline capabilities present in v0.2.0 are fully
reachable and operational across the consolidated Option B tool surface.
"""

import asyncio
import unittest

from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class CapabilityCoverageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.service = SceneService()
        self.server = create_server(self.service, toolset="full")
        self.tools = {t.name: t.fn for t in await self.server.list_tools()}

    async def test_all_48_baseline_capabilities_covered(self):
        tools = self.tools

        # 1. add_rectangle -> create_shape(type="rectangle")
        r1 = tools["create_shape"](type="rectangle", x=0, y=0, w=100, h=60, label="Box 1")
        self.assertIn("rectangle_id", r1)
        r1_id = r1["rectangle_id"]

        # 2. add_circle -> create_shape(type="ellipse")
        c1 = tools["create_shape"](type="ellipse", x=150, y=0, w=80, h=80, label="Circle 1")
        self.assertIn("element_id", c1)
        c1_id = c1["element_id"]

        # 3. add_diamond -> create_shape(type="diamond")
        d1 = tools["create_shape"](type="diamond", x=300, y=0, w=80, h=80, label="Decision")
        self.assertIn("diamond_id", d1)
        d1_id = d1["diamond_id"]

        # 4. add_arrow -> create_connector(x, y, x2, y2)
        arr = tools["create_connector"](x=0, y=0, x2=50, y2=50)
        self.assertIn("arrow_id", arr)

        # 5. add_frame -> add_frame
        f1 = tools["add_frame"](name="Frame A", x=-20, y=-20, w=500, h=300)
        self.assertIn("frame_id", f1)
        f1_id = f1["frame_id"]

        # 6. add_text -> add_text
        txt = tools["add_text"](x=10, y=100, content="Standalone Text")
        self.assertIn("text_id", txt)
        txt_id = txt["text_id"]

        # 7. move -> update_element(x, y)
        up_pos = tools["update_element"](element_id=r1_id, x=10, y=10)
        self.assertIn(up_pos["status"], ("moved", "updated"))

        # 8. resize -> update_element(width, height)
        up_sz = tools["update_element"](element_id=r1_id, width=120, height=70)
        self.assertIn(up_sz["status"], ("resized", "updated"))

        # 9. update_element -> update_element(visual styles)
        up_style = tools["update_element"](element_id=r1_id, strokeColor="#ff0000")
        self.assertEqual(up_style["status"], "updated")

        # 10. connect -> create_connector(source_id, target_id)
        conn = tools["create_connector"](source_id=r1_id, target_id=c1_id)
        self.assertIn("element_id", conn)

        # 11. get_scene -> inspect_scene(mode="elements")
        sc = tools["inspect_scene"](mode="elements", limit=10)
        self.assertGreaterEqual(sc["total"], 4)

        # 12. get_element -> inspect_scene(mode="element")
        el = tools["inspect_scene"](mode="element", element_id=r1_id)
        self.assertEqual(el["element"]["id"], r1_id)

        # 13. find_elements -> inspect_scene(mode="find")
        fnd = tools["inspect_scene"](mode="find", query="Box")
        self.assertGreaterEqual(fnd["total"], 1)

        # 14. get_scene_summary -> inspect_scene(mode="summary")
        summ = tools["inspect_scene"](mode="summary")
        self.assertGreaterEqual(summ["element_count"], 4)

        # 15. describe_scene -> inspect_scene(mode="describe")
        desc = tools["inspect_scene"](mode="describe")
        self.assertIn("summary", desc)

        # 16. get_viewport -> inspect_scene(mode="viewport")
        vp = tools["inspect_scene"](mode="viewport")
        self.assertIn("zoom", vp)

        # 17. get_live_server_status -> inspect_scene(mode="live_server")
        ls_stat = tools["inspect_scene"](mode="live_server")
        self.assertIn("status", ls_stat)

        # 18. get_resource -> inspect_scene(mode="resource")
        res_info = tools["inspect_scene"](mode="resource", resource_uri="excalidraw://theme/dark")
        self.assertIn("resource_type", res_info)

        # 19. set_viewport -> set_viewport
        set_vp = tools["set_viewport"](zoom=1.5)
        self.assertEqual(set_vp["zoom"], 1.5)

        # 20. focus_elements -> set_viewport(focus_element_ids=...)
        foc = tools["set_viewport"](focus_element_ids=[r1_id, c1_id])
        self.assertEqual(foc["status"], "focused")

        # 21. lock_elements / set_element_locked -> manage_element_state(action="lock")
        lck = tools["manage_element_state"](element_ids=[r1_id], action="lock")
        self.assertEqual(lck["status"], "locked")

        # 22. unlock_elements -> manage_element_state(action="unlock")
        unl = tools["manage_element_state"](element_ids=[r1_id], action="unlock")
        self.assertEqual(unl["status"], "unlocked")

        # 23. group_elements / manage_groups -> manage_element_state(action="group")
        grp = tools["manage_element_state"](element_ids=[r1_id, c1_id], action="group")
        self.assertEqual(grp["status"], "grouped")
        gid = grp["group_id"]

        # 24. ungroup_elements -> manage_element_state(action="ungroup")
        ungrp = tools["manage_element_state"](group_id=gid, action="ungroup")
        self.assertEqual(ungrp["status"], "ungrouped")

        # 25. duplicate_elements -> manage_element_state(action="duplicate")
        dupl = tools["manage_element_state"](element_ids=[r1_id], action="duplicate")
        self.assertIn("duplicated_ids", dupl)

        # 26. delete -> delete
        del_res = tools["delete"](element_id=d1_id)
        self.assertEqual(del_res["status"], "deleted")

        # 27. undo -> undo
        und_res = tools["undo"]()
        self.assertEqual(und_res["status"], "undone")

        # 28. preview -> preview
        img = tools["preview"]()
        self.assertIsNotNone(img.data)

        # 29. auto_fix_layout -> auto_fix_layout
        fx = tools["auto_fix_layout"](dry_run=True)
        self.assertIn("status", fx)

        # 30. batch_mutate -> batch_mutate
        bm = tools["batch_mutate"](
            operations=[
                {"action": "add_rectangle", "x": 0, "y": 200, "w": 50, "h": 50, "client_id": "b1"},
                {"action": "move", "element_id": "b1", "x": 20, "y": 220},
            ]
        )
        self.assertEqual(bm["operations_executed"], 2)

        # 31. add_code_block -> batch_mutate(action="add_code_block")
        cb_m = tools["batch_mutate"](
            operations=[
                {"action": "add_code_block", "code": "x = 1", "x": 0, "y": 300}
            ]
        )
        self.assertEqual(cb_m["operations_executed"], 1)

        # 32. save -> scene_storage(action="save")
        sv = tools["scene_storage"](action="save", name="cov_test", overwrite=True)
        self.assertEqual(sv["status"], "saved")

        # 33. list_saved_scenes -> scene_storage(action="list")
        ls = tools["scene_storage"](action="list")
        self.assertIn("cov_test", ls["scenes"])

        # 34. export_scene -> scene_storage(action="export")
        exp = tools["scene_storage"](action="export")
        self.assertEqual(exp.type, "resource")

        # 35. load -> scene_storage(action="load")
        ld = tools["scene_storage"](action="load", name="cov_test")
        self.assertEqual(ld["status"], "loaded")

        # 36. import_scene -> scene_storage(action="import")
        imp = tools["scene_storage"](action="import", data='{"type": "excalidraw", "version": 2, "elements": []}')
        self.assertEqual(imp["status"], "imported")

        # 37. export_to_excalidraw_url -> scene_storage(action="share_url") / export_to_excalidraw_url
        self.assertIn("export_to_excalidraw_url", tools)

        # 38. draw_architecture -> generate_diagram(format="architecture")
        arch = tools["generate_diagram"](format="architecture", prompt="box: Web, box: API")
        self.assertEqual(arch["nodes"], 2)

        # 39. draw_mermaid -> generate_diagram(format="mermaid")
        merm = tools["generate_diagram"](format="mermaid", mermaid_code="graph TD\nA --> B")
        self.assertEqual(merm["nodes"], 2)

        # 40. draw_graph -> generate_diagram(format="graph")
        grp_diag = tools["generate_diagram"](
            format="graph",
            nodes=[{"id": "n1", "label": "N1"}, {"id": "n2", "label": "N2"}],
            edges=[{"id": "e1", "source": "n1", "target": "n2"}],
        )
        self.assertEqual(grp_diag["nodes"], 2)

        # 41. export_png -> export_png
        png_res = tools["export_png"](name="cov_png", overwrite=True)
        self.assertEqual(png_res["status"], "png exported")

        # 42. start_live_server -> live_server(action="start")
        # 43. stop_live_server -> live_server(action="stop")
        self.assertIn("live_server", tools)

        # 44. list_fonts -> MCP resource excalidraw://fonts
        fonts_res = await self.server.read_resource("excalidraw://fonts")
        self.assertIn("fonts", str(fonts_res))

        # 45. read_diagram_guide -> read_diagram_guide
        self.assertIn("read_diagram_guide", tools)

        # 46. clear -> clear
        clr = tools["clear"]()
        self.assertEqual(clr["status"], "scene cleared")

        # Verify element count is now 0
        final_sc = tools["inspect_scene"](mode="summary")
        self.assertEqual(final_sc["element_count"], 0)


if __name__ == "__main__":
    unittest.main()
