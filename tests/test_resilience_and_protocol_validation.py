"""Validation tests for state resilience and protocol contract enhancements.

Verifies:
- Font registry LRU cache invalidation upon forced discovery
- Viewport and camera mutations decoupled from drawing undo history
- Unsupported Mermaid diagram header detection and actionable syntax guidance
- Scene inspection tool descriptions and export guidance contracts
"""

import asyncio
import unittest

from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.fonts import FontRegistry
from excalidraw_mcp.mermaid import parse_mermaid
from excalidraw_mcp.server import create_server
from excalidraw_mcp.service import SceneService


class ResilienceAndProtocolValidationTests(unittest.TestCase):
    def setUp(self):
        self.service = SceneService()

    def test_font_cache_clear_on_discover_force(self):
        """Ensure discover(force=True) invalidates load_font LRU cache."""
        reg = FontRegistry()
        reg.load_font("sans-serif", 14)
        info1 = reg.load_font.cache_info()
        self.assertGreaterEqual(info1.currsize, 1)

        # Forced rediscovery must flush the LRU cache
        reg.discover(force=True)
        info2 = reg.load_font.cache_info()
        self.assertEqual(info2.currsize, 0)

    def test_viewport_decoupled_from_undo_history(self):
        """Verify set_viewport and focus_elements bypass undo history stack."""
        # 1. Add a shape (should be tracked in undo history)
        r = self.service.add_shape("rectangle", 100, 100, 200, 100, label="Box 1")
        self.assertEqual(self.service.state.history_depth, 1)

        # 2. Set camera viewport (transient camera state must not increment history)
        self.service.set_viewport(scroll_x=50.0, scroll_y=50.0, zoom=1.5)
        self.assertEqual(self.service.state.history_depth, 1)

        # 3. Focus elements (framing camera must not increment history)
        self.service.focus_elements([r["rectangle_id"]])
        self.assertEqual(self.service.state.history_depth, 1)

        # 4. Calling undo should revert the shape creation, not the viewport pan
        undo_res = self.service.undo()
        self.assertEqual(undo_res["status"], "undone")

        # Scene should now have 0 active shapes
        doc = self.service.state.document()
        active_shapes = [el for el in doc["elements"] if not el.get("isDeleted")]
        self.assertEqual(len(active_shapes), 0)

    def test_mermaid_actionable_error_on_unsupported_diagrams(self):
        """Ensure non-flowchart Mermaid diagram headers produce actionable errors."""
        unsupported_snippets = [
            "sequenceDiagram\nAlice->>Bob: Hello",
            "classDiagram\nclass Animal",
            "stateDiagram\n[*] --> Still",
            "stateDiagram-v2\n[*] --> State1",
            "erDiagram\nCUSTOMER ||--o{ ORDER : places",
            "gantt\ntitle A Gantt Diagram",
            "gitGraph\ncommit",
        ]
        for snippet in unsupported_snippets:
            with self.subTest(diagram=snippet.splitlines()[0]):
                with self.assertRaisesRegex(
                    SceneError,
                    r"are not supported yet\. Only flowchart and graph diagrams",
                ):
                    parse_mermaid(snippet)

    def test_architecture_result_and_inspection_tool_descriptions(self):
        """Verify ArchitectureResult next_step export guidance and inspection tool contracts."""
        arch = self.service.draw_architecture("box: Client, box: Server")
        self.assertIn("export_to_excalidraw_url", arch["next_step"])

        mcp = create_server(self.service)
        tools = asyncio.run(mcp.list_tools())
        tool_map = {t.name: t.description for t in tools}

        self.assertIn("inspect_scene", tool_map)
        # Verify inspect_scene guides models on inspection roles
        self.assertIn("metrics", tool_map["inspect_scene"])
        self.assertIn("spatial descriptions", tool_map["inspect_scene"])
