"""Tests for MCP skills resources and prompts registration, discovery, and execution."""

from __future__ import annotations

import json
import pytest
from fastmcp.exceptions import ResourceError

from excalidraw_mcp.server import create_server
from excalidraw_mcp.skills import (
    read_reference_content,
    read_skill_content,
)
from tests.test_skills_distribution import (
    EXPECTED_REFERENCES,
    EXPECTED_SKILLS,
)


@pytest.fixture
def server():
    """Create a test FastMCP server instance with registered tools, resources, and prompts."""
    return create_server()


@pytest.mark.asyncio
async def test_mcp_resources_listing(server):
    """Verify that all skills and reference documents are registered as discoverable resources."""
    resources = await server.list_resources()
    uris = {str(r.uri) for r in resources}

    # Index
    assert "exca-mcp://skills/index" in uris

    # All six skills
    for name in EXPECTED_SKILLS:
        assert f"exca-mcp://skills/{name}" in uris

    # All reference documents
    for skill_name, refs in EXPECTED_REFERENCES.items():
        for ref in refs:
            assert f"exca-mcp://skills/{skill_name}/references/{ref}" in uris


@pytest.mark.asyncio
async def test_mcp_read_skills_index(server):
    """Verify reading and parsing the skills index resource."""
    result = await server.read_resource("exca-mcp://skills/index")
    assert len(result.contents) == 1
    content_item = result.contents[0]
    assert content_item.mime_type == "application/json"

    data = json.loads(content_item.content)
    assert data["total_skills"] == 6
    assert len(data["skills"]) == 6
    assert "recommended_workflow" in data

    skill_names = {s["name"] for s in data["skills"]}
    assert skill_names == set(EXPECTED_SKILLS)


@pytest.mark.asyncio
async def test_mcp_read_all_skill_resources(server):
    """Verify reading every skill resource matches the canonical file content."""
    for name in EXPECTED_SKILLS:
        uri = f"exca-mcp://skills/{name}"
        result = await server.read_resource(uri)
        assert len(result.contents) == 1
        item = result.contents[0]
        assert item.mime_type == "text/markdown"

        expected_text = read_skill_content(name)
        assert item.content == expected_text


@pytest.mark.asyncio
async def test_mcp_read_all_reference_resources(server):
    """Verify reading every reference document resource matches canonical content."""
    for skill_name, refs in EXPECTED_REFERENCES.items():
        for ref in refs:
            uri = f"exca-mcp://skills/{skill_name}/references/{ref}"
            result = await server.read_resource(uri)
            assert len(result.contents) == 1
            item = result.contents[0]
            assert item.mime_type == "text/markdown"

            expected_text = read_reference_content(skill_name, ref)
            assert item.content == expected_text


@pytest.mark.asyncio
async def test_mcp_invalid_resource_handling(server):
    """Verify unknown skill or reference resource URIs raise ResourceError."""
    with pytest.raises(ResourceError):
        await server.read_resource("exca-mcp://skills/nonexistent-skill-abc")

    with pytest.raises(ResourceError):
        await server.read_resource(
            "exca-mcp://skills/architecture-diagrams/references/nonexistent-ref"
        )


@pytest.mark.asyncio
async def test_mcp_prompts_listing(server):
    """Verify that all five required task prompts are registered."""
    prompts = await server.list_prompts()
    prompt_names = {p.name for p in prompts}

    expected_prompts = {
        "create_architecture_diagram",
        "create_flowchart",
        "plan_diagram",
        "edit_existing_diagram",
        "verify_and_export_diagram",
    }
    assert expected_prompts.issubset(prompt_names)


@pytest.mark.asyncio
async def test_mcp_prompt_create_architecture_diagram(server):
    """Verify create_architecture_diagram prompt rendering and skill inclusion."""
    p = await server.get_prompt("create_architecture_diagram")
    rendered = await p.render(
        {
            "system_description": "Payments & Billing Gateway",
            "style": "modern",
            "output_name": "payments-arch",
        }
    )
    assert len(rendered.messages) == 1
    text = rendered.messages[0].content.text

    assert "Payments & Billing Gateway" in text
    assert "payments-arch" in text
    assert "add_frame" in text
    assert "add_rectangle" in text
    assert "connect" in text
    assert "auto_fix_layout" in text
    assert "60-30-10" in text
    assert "exca-mcp://skills/architecture-diagrams" in text


@pytest.mark.asyncio
async def test_mcp_prompt_create_flowchart(server):
    """Verify create_flowchart prompt rendering and flowchart-specific rules."""
    p = await server.get_prompt("create_flowchart")
    rendered = await p.render(
        {
            "process_description": "User Onboarding and KYC Verification",
            "direction": "TB",
            "output_name": "kyc-flow",
        }
    )
    assert len(rendered.messages) == 1
    text = rendered.messages[0].content.text

    assert "User Onboarding and KYC Verification" in text
    assert "kyc-flow" in text
    assert "Single Start Node" in text
    assert "add_diamond" in text
    assert "elbowed=True" in text
    assert "exca-mcp://skills/flowcharts-and-processes" in text


@pytest.mark.asyncio
async def test_mcp_prompt_plan_diagram(server):
    """Verify plan_diagram prompt rendering and upfront planning rules."""
    p = await server.get_prompt("plan_diagram")
    rendered = await p.render(
        {
            "request": "Design an event-driven telemetry pipeline",
            "diagram_type": "event-pipeline",
        }
    )
    assert len(rendered.messages) == 1
    text = rendered.messages[0].content.text

    assert "event-driven telemetry pipeline" in text
    assert "Density Cap" in text
    assert "15 nodes" in text
    assert "exca-mcp://skills/diagram-planning" in text


@pytest.mark.asyncio
async def test_mcp_prompt_edit_existing_diagram(server):
    """Verify edit_existing_diagram prompt rendering and non-destructive editing rules."""
    p = await server.get_prompt("edit_existing_diagram")
    rendered = await p.render(
        {
            "instructions": "Add Redis caching cluster between API and Postgres",
            "scene_name": "production-v1",
        }
    )
    assert len(rendered.messages) == 1
    text = rendered.messages[0].content.text

    assert "Redis caching cluster" in text
    assert "production-v1" in text
    assert "get_scene" in text
    assert "update_element" in text
    assert "auto_fix_layout" in text
    assert "exca-mcp://skills/excalidraw-workflow" in text


@pytest.mark.asyncio
async def test_mcp_prompt_verify_and_export_diagram(server):
    """Verify verify_and_export_diagram prompt rendering and quality gate rules."""
    p = await server.get_prompt("verify_and_export_diagram")
    rendered = await p.render(
        {
            "output_name": "final-architecture",
            "directory": "docs/assets",
        }
    )
    assert len(rendered.messages) == 1
    text = rendered.messages[0].content.text

    assert "final-architecture" in text
    assert "docs/assets" in text
    assert "auto_fix_layout" in text
    assert "preview" in text
    assert "export_png" in text
    assert "exca-mcp://skills/verify-and-editable-handoff" in text


@pytest.mark.asyncio
async def test_existing_mcp_tools_compatibility(server):
    """Verify that existing MCP tools work properly alongside skills resources and prompts."""
    # Create frame and rectangles
    f = await server.call_tool("add_frame", {"name": "Test Frame", "x": 100.0, "y": 100.0, "w": 400.0, "h": 200.0})
    frame_id = f.structured_content["frame_id"]

    r1 = await server.call_tool("add_rectangle", {"x": 120.0, "y": 140.0, "w": 140.0, "h": 50.0, "label": "Box A", "frame_id": frame_id})
    r2 = await server.call_tool("add_rectangle", {"x": 320.0, "y": 140.0, "w": 140.0, "h": 50.0, "label": "Box B", "frame_id": frame_id})
    id1 = r1.structured_content["rectangle_id"]
    id2 = r2.structured_content["rectangle_id"]

    conn = await server.call_tool("connect", {"source_id": id1, "target_id": id2, "label": "Link", "elbowed": True})
    assert "arrow_id" in conn.structured_content

    diag = await server.call_tool("auto_fix_layout", {"dry_run": True})
    assert diag.structured_content["status"] == "no_changes_needed"
