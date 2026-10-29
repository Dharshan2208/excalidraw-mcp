import asyncio
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from fastmcp.exceptions import ToolError

from excalidraw_mcp.elements import rect
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document
from excalidraw_mcp.service import SceneService
from excalidraw_mcp.state import SceneState
from excalidraw_mcp.server import create_server


class StateTests(unittest.TestCase):
    def setUp(self):
        self.state = SceneState()
        self.service = SceneService(self.state)

    def test_all_read_surfaces_are_detached(self):
        element = rect(0, 0, 50, 50)
        element_id = self.state.add(element)
        element["x"] = 200
        self.state.get(element_id)["x"] = 300
        self.state.all()[0]["x"] = 400
        self.state.elements.clear()
        self.state.document()["elements"].clear()
        self.assertEqual(self.state.get(element_id)["x"], 0)
        self.assertEqual(len(self.state.all()), 1)

    def test_duplicate_ids_rejected_without_partial_commit(self):
        element = rect(0, 0, 50, 50)
        self.state.add(element)
        before = self.state.document()
        with self.assertRaises(SceneError):
            self.state.add_many([rect(1, 1, 20, 20), element])
        self.assertEqual(self.state.document(), before)
        with self.assertRaises(SceneError):
            self.state.replace(new_document([element, element]))
        self.assertEqual(self.state.document(), before)

    def test_callback_error_and_validation_error_roll_back(self):
        self.state.add(rect(0, 0, 50, 50))
        before, revision = self.state.document(), self.state.revision

        def fail(document):
            document["elements"].clear()
            raise RuntimeError("failed")

        with self.assertRaises(RuntimeError):
            self.state.apply(fail)
        with self.assertRaises(SceneError):
            self.state.apply(lambda document: document["elements"].append({}))
        self.assertEqual(self.state.document(), before)
        self.assertEqual(self.state.revision, revision)

    def test_nested_mutation_cannot_commit_before_outer_failure(self):
        self.state.add(rect(0, 0, 50, 50))
        before = self.state.document()
        with self.assertRaisesRegex(SceneError, "Nested"):
            self.state.apply(lambda document: self.state.clear())
        self.assertEqual(self.state.document(), before)

    def test_invalid_add_is_a_domain_error(self):
        with self.assertRaises(SceneError):
            self.state.add({})
        self.assertEqual(self.state.all(), [])

    def test_element_order_and_index_survive_delete_and_replace(self):
        ids = [self.state.add(rect(i, 0, 10, 10)) for i in range(3)]
        self.service.delete(ids[1])
        self.assertIsNone(self.state.get(ids[1]))
        self.assertEqual([el["id"] for el in self.state.all()], [ids[0], ids[2]])
        self.state.replace(new_document())
        self.assertIsNone(self.state.get(ids[0]))

    def test_mutations_bump_only_changed_elements(self):
        group = self.service.add_shape("rectangle", 0, 0, 100, 100, "label")
        other = self.state.add(rect(300, 0, 50, 50))
        before = {el["id"]: el for el in self.state.all()}
        self.service.move(group["rectangle_id"], 10, 20)
        for key in (group["rectangle_id"], group["label_id"]):
            after = self.state.get(key)
            self.assertEqual(after["version"], before[key]["version"] + 1)
            self.assertGreater(after["updated"], before[key]["updated"])
            self.assertIsInstance(after["versionNonce"], int)
        self.assertEqual(self.state.get(other), before[other])
        before = self.state.document()
        self.service.move(group["rectangle_id"], 10, 20)
        self.assertEqual(self.state.document(), before)

    def test_parallel_adds_do_not_lose_elements_or_labels(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda i: self.service.add_shape(
                        "rectangle", i * 100, 0, 50, 50, str(i)
                    ),
                    range(40),
                )
            )
        self.assertEqual(len(self.state.all()), 80)
        for result in results:
            shape = self.state.get(result["rectangle_id"])
            self.assertEqual(
                shape["boundElements"], [{"id": result["label_id"], "type": "text"}]
            )
            self.assertEqual(
                self.state.get(result["label_id"])["containerId"], shape["id"]
            )

    def test_read_waits_for_complete_transaction(self):
        result = self.service.add_shape("rectangle", 0, 0, 100, 100, "label")
        edited, release, reading = Event(), Event(), Event()

        def mutate(document):
            document["elements"][0]["x"] = 100
            edited.set()
            if not release.wait(3):
                raise RuntimeError("test timed out")
            document["elements"][1]["x"] += 100

        def read():
            reading.set()
            return self.state.document()

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(self.state.apply, mutate)
            try:
                self.assertTrue(edited.wait(3))
                reader = pool.submit(read)
                self.assertTrue(reading.wait(3))
                self.assertFalse(reader.done())
            finally:
                release.set()
            writer.result(timeout=3)
            snapshot = reader.result(timeout=3)
        self.assertEqual(snapshot["elements"][0]["x"], 100)
        self.assertEqual(snapshot["elements"][1]["x"], 120)
        self.assertEqual(snapshot["elements"][1]["containerId"], result["rectangle_id"])

    def test_replacement_revision_guard_preserves_newer_work(self):
        revision = self.state.revision
        self.state.add(rect(0, 0, 10, 10))
        before = self.state.document()
        with self.assertRaisesRegex(SceneError, "changed"):
            self.state.replace(new_document(), expected_revision=revision)
        self.assertEqual(self.state.document(), before)

    def test_servers_have_isolated_state_and_keep_tool_names(self):
        async def tools(server):
            return {tool.name: tool.fn for tool in await server.list_tools()}

        first = asyncio.run(tools(create_server()))
        second = asyncio.run(tools(create_server()))
        self.assertEqual(
            set(first),
            {
                "add_rectangle",
                "add_circle",
                "add_diamond",
                "add_arrow",
                "add_text",
                "clear",
                "delete",
                "move",
                "resize",
                "update_element",
                "connect",
                "undo",
                "save",
                "load",
                "preview",
                "draw_architecture",
                "draw_graph",
                "export_scene",
                "get_scene",
                "get_element",
                "list_saved_scenes",
                "add_frame",
                "find_elements",
                "batch_mutate",
                "export_png",
                "add_code_block",
                "list_fonts",
                "lock_elements",
                "unlock_elements",
                "group_elements",
                "ungroup_elements",
                "draw_mermaid",
                "get_viewport",
                "set_viewport",
                "focus_elements",
                "get_scene_summary",
                "export_to_excalidraw_url",
                "describe_scene",
                "get_canvas_screenshot",
                "get_resource",
                "read_diagram_guide",
                "duplicate_elements",
                "import_scene",
                "start_live_server",
                "stop_live_server",
                "get_live_server_status",
                "auto_fix_layout",
            },
        )
        result = first["add_rectangle"](0, 0, 10, 10, label="A")
        with self.assertRaisesRegex(ToolError, "not found"):
            second["move"](result["rectangle_id"], 20, 20)
        first["move"](result["rectangle_id"], 20, 20)

    def test_history_limit_configuration_is_validated(self):
        with patch.dict(os.environ, {"EXCALIDRAW_HISTORY_LIMIT": "2"}):
            self.assertEqual(SceneState()._max_history, 2)
        for value in ("0", "101", "invalid"):
            with (
                self.subTest(value=value),
                patch.dict(os.environ, {"EXCALIDRAW_HISTORY_LIMIT": value}),
            ):
                with self.assertRaises(ValueError):
                    SceneState()


if __name__ == "__main__":
    unittest.main()
