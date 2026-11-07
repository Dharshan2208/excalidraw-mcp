"""Tests for MCP skills resources and prompts registration, discovery, and execution."""

from __future__ import annotations

import json
import unittest
from fastmcp.exceptions import NotFoundError, ResourceError

from excalidraw_mcp.server import create_server
from excalidraw_mcp.skills import (
    read_reference_content,
    read_skill_content,
)
from tests.test_skills_distribution import (
    EXPECTED_REFERENCES,
    EXPECTED_SKILLS,
)


class SkillsMCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        """Create a test FastMCP server instance for each test."""
        self.server = create_server()

    async def test_mcp_resources_listing(self):
        """Verify that all skills and reference documents are registered as discoverable resources."""
        resources = await self.server.list_resources()
        uris = {str(r.uri) for r in resources}

        # Index
        self.assertIn("exca-mcp://skills/index", uris)

        # All six skills
        for name in EXPECTED_SKILLS:
            self.assertIn(f"exca-mcp://skills/{name}", uris)

        # All reference documents
        for skill_name, refs in EXPECTED_REFERENCES.items():
            for ref in refs:
                self.assertIn(f"exca-mcp://skills/{skill_name}/references/{ref}", uris)

    async def test_mcp_read_skills_index(self):
        """Verify reading and parsing the skills index resource."""
        result = await self.server.read_resource("exca-mcp://skills/index")
        self.assertEqual(len(result.contents), 1)
        content_item = result.contents[0]
        self.assertEqual(content_item.mime_type, "application/json")

        data = json.loads(content_item.content)
        self.assertEqual(data["total_skills"], 6)
        self.assertEqual(len(data["skills"]), 6)
        self.assertIn("recommended_workflow", data)

        skill_names = {s["name"] for s in data["skills"]}
        self.assertEqual(skill_names, set(EXPECTED_SKILLS))

    async def test_mcp_read_all_skill_resources(self):
        """Verify reading every skill resource matches the canonical file content."""
        for name in EXPECTED_SKILLS:
            uri = f"exca-mcp://skills/{name}"
            result = await self.server.read_resource(uri)
            self.assertEqual(len(result.contents), 1)
            item = result.contents[0]
            self.assertEqual(item.mime_type, "text/markdown")

            expected_text = read_skill_content(name)
            self.assertEqual(item.content, expected_text)

    async def test_mcp_read_all_reference_resources(self):
        """Verify reading every reference document resource matches canonical content."""
        for skill_name, refs in EXPECTED_REFERENCES.items():
            for ref in refs:
                uri = f"exca-mcp://skills/{skill_name}/references/{ref}"
                result = await self.server.read_resource(uri)
                self.assertEqual(len(result.contents), 1)
                item = result.contents[0]
                self.assertEqual(item.mime_type, "text/markdown")

                expected_text = read_reference_content(skill_name, ref)
                self.assertEqual(item.content, expected_text)

    async def test_mcp_invalid_resource_handling(self):
        """Verify unknown skill or reference resource URIs raise NotFoundError or ResourceError."""
        with self.assertRaises((ResourceError, NotFoundError)):
            await self.server.read_resource("exca-mcp://skills/nonexistent-skill-abc")

        with self.assertRaises((ResourceError, NotFoundError)):
            await self.server.read_resource(
                "exca-mcp://skills/architecture-diagrams/references/nonexistent-ref"
            )

    async def test_mcp_prompts_listing(self):
        """Verify that all five required task prompts are registered."""
        prompts = await self.server.list_prompts()
        prompt_names = {p.name for p in prompts}

        expected_prompts = {
            "create_architecture_diagram",
            "create_flowchart",
            "plan_diagram",
            "edit_existing_diagram",
            "verify_and_export_diagram",
        }
        self.assertTrue(expected_prompts.issubset(prompt_names))

    async def test_mcp_prompt_create_architecture_diagram(self):
        """Verify create_architecture_diagram prompt rendering and skill inclusion."""
        p = await self.server.get_prompt("create_architecture_diagram")
        rendered = await p.render(
            {
                "system_description": "Payments & Billing Gateway",
                "style": "modern",
                "output_name": "payments-arch",
            }
        )
        self.assertEqual(len(rendered.messages), 1)
        text = rendered.messages[0].content.text

        self.assertIn("Payments & Billing Gateway", text)
        self.assertIn("payments-arch", text)
        self.assertIn("add_frame", text)
        self.assertIn("add_rectangle", text)
        self.assertIn("connect", text)
        self.assertIn("auto_fix_layout", text)
        self.assertIn("60-30-10", text)
        self.assertIn("exca-mcp://skills/architecture-diagrams", text)

    async def test_mcp_prompt_create_flowchart(self):
        """Verify create_flowchart prompt rendering and flowchart-specific rules."""
        p = await self.server.get_prompt("create_flowchart")
        rendered = await p.render(
            {
                "process_description": "User Onboarding and KYC Verification",
                "direction": "TB",
                "output_name": "kyc-flow",
            }
        )
        self.assertEqual(len(rendered.messages), 1)
        text = rendered.messages[0].content.text

        self.assertIn("User Onboarding and KYC Verification", text)
        self.assertIn("kyc-flow", text)
        self.assertIn("Single Start Node", text)
        self.assertIn("add_diamond", text)
        self.assertIn("elbowed=True", text)
        self.assertIn("exca-mcp://skills/flowcharts-and-processes", text)

    async def test_mcp_prompt_plan_diagram(self):
        """Verify plan_diagram prompt rendering and upfront planning rules."""
        p = await self.server.get_prompt("plan_diagram")
        rendered = await p.render(
            {
                "request": "Design an event-driven telemetry pipeline",
                "diagram_type": "event-pipeline",
            }
        )
        self.assertEqual(len(rendered.messages), 1)
        text = rendered.messages[0].content.text

        self.assertIn("event-driven telemetry pipeline", text)
        self.assertIn("Density Cap", text)
        self.assertIn("15 nodes", text)
        self.assertIn("exca-mcp://skills/diagram-planning", text)

    async def test_mcp_prompt_edit_existing_diagram(self):
        """Verify edit_existing_diagram prompt rendering and non-destructive editing rules."""
        p = await self.server.get_prompt("edit_existing_diagram")
        rendered = await p.render(
            {
                "instructions": "Add Redis caching cluster between API and Postgres",
                "scene_name": "production-v1",
            }
        )
        self.assertEqual(len(rendered.messages), 1)
        text = rendered.messages[0].content.text

        self.assertIn("Redis caching cluster", text)
        self.assertIn("production-v1", text)
        self.assertIn("get_scene", text)
        self.assertIn("update_element", text)
        self.assertIn("auto_fix_layout", text)
        self.assertIn("exca-mcp://skills/excalidraw-workflow", text)

    async def test_mcp_prompt_verify_and_export_diagram(self):
        """Verify verify_and_export_diagram prompt rendering and quality gate rules."""
        p = await self.server.get_prompt("verify_and_export_diagram")
        rendered = await p.render(
            {
                "output_name": "final-architecture",
                "directory": "docs/assets",
            }
        )
        self.assertEqual(len(rendered.messages), 1)
        text = rendered.messages[0].content.text

        self.assertIn("final-architecture", text)
        self.assertIn("docs/assets", text)
        self.assertIn("auto_fix_layout", text)
        self.assertIn("preview", text)
        self.assertIn("export_png", text)
        self.assertIn("exca-mcp://skills/verify-and-editable-handoff", text)

    async def test_existing_mcp_tools_compatibility(self):
        """Verify that existing MCP tools work properly alongside skills resources and prompts."""
        f = await self.server.call_tool(
            "add_frame", {"name": "Test Frame", "x": 100.0, "y": 100.0, "w": 400.0, "h": 200.0}
        )
        frame_id = f.structured_content["frame_id"]

        r1 = await self.server.call_tool(
            "add_rectangle",
            {"x": 120.0, "y": 140.0, "w": 140.0, "h": 50.0, "label": "Box A", "frame_id": frame_id},
        )
        r2 = await self.server.call_tool(
            "add_rectangle",
            {"x": 320.0, "y": 140.0, "w": 140.0, "h": 50.0, "label": "Box B", "frame_id": frame_id},
        )
        id1 = r1.structured_content["rectangle_id"]
        id2 = r2.structured_content["rectangle_id"]

        conn = await self.server.call_tool(
            "connect", {"source_id": id1, "target_id": id2, "label": "Link", "elbowed": True}
        )
        self.assertIn("arrow_id", conn.structured_content)

        diag = await self.server.call_tool("auto_fix_layout", {"dry_run": True})
        self.assertEqual(diag.structured_content["status"], "no_changes_needed")


if __name__ == "__main__":
    unittest.main()
