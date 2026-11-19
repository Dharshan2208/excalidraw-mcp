"""Standalone prototype of Option B (Balanced Surface) FastMCP Server.

Usage:
    uv run --with tiktoken python benchmarks/prototype_option_b.py
"""

import asyncio
import json
import sys
from typing import Annotated, Any, Literal

try:
    import tiktoken
except ImportError:
    print("Error: 'tiktoken' is required for token benchmarks.")
    print("Run with: uv run --with tiktoken python benchmarks/prototype_option_b.py")
    sys.exit(1)

from fastmcp import FastMCP, Client
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

enc_o200k = tiktoken.get_encoding("o200k_base")
enc_cl100k = tiktoken.get_encoding("cl100k_base")


def tok(text: str):
    return {
        "bytes": len(text.encode("utf-8")),
        "o200k": len(enc_o200k.encode(text)),
        "cl100k": len(enc_cl100k.encode(text)),
    }


MUTATING = ToolAnnotations(destructiveHint=False, idempotentHint=False, openWorldHint=False)
DESTRUCTIVE = ToolAnnotations(destructiveHint=True, idempotentHint=False, openWorldHint=False)
IDEMPOTENT = ToolAnnotations(destructiveHint=False, idempotentHint=True, openWorldHint=False)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

Coordinate = Annotated[float, Field(ge=-100_000, le=100_000, description="Canvas coordinate in px")]
Dimension = Annotated[float, Field(gt=0, le=100_000, description="Dimension size in px")]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$|^transparent$", description="Hex color or 'transparent'")]
ShapeType = Literal["rectangle", "ellipse", "diamond"]
FillStyle = Literal["solid", "hachure", "cross-hatch", "zigzag"]
StrokeStyle = Literal["solid", "dashed", "dotted"]
Roundness = Literal["adaptive", "round", "sharp"]
FontFamily = Literal["excalifont", "sans-serif", "monospace", "comic-shanns"]


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Unique node identifier")
    label: str = Field(description="Node text label")
    shape: ShapeType = "rectangle"
    cluster: str | None = Field(default=None, description="Optional cluster / frame ID")
    strokeColor: Color | None = None
    backgroundColor: Color | None = None
    fillStyle: FillStyle | None = None


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: str = Field(description="Source node ID")
    target: str = Field(description="Target node ID")
    label: str = ""
    elbowed: bool = False
    strokeColor: Color | None = None


class GraphCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(description="Cluster container ID")
    label: str = Field(description="Cluster header title")


class BatchOp(BaseModel):
    model_config = ConfigDict(extra="allow")
    action: Literal["add_shape", "connect", "add_text", "add_frame", "update", "move", "resize", "delete", "lock", "group"]
    client_id: str | None = Field(default=None, description="Temporary client reference ID for binding")
    type: ShapeType | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    label: str | None = None
    text: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    element_id: str | None = None
    element_ids: list[str] | None = None
    elbowed: bool | None = None


def build_option_b_server(typed_generator: bool = True, strip_output_schemas: bool = True) -> FastMCP:
    m = FastMCP("Excalidraw Option B")

    # --- CORE TOOLS (12 TOOLS) ---

    # 1. create_shape (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def create_shape(
        type: ShapeType,
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension,
        label: str = "",
        frame_id: str | None = None,
        roundness: Roundness | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: int | None = None,
        font_family: FontFamily | None = None,
        font_size: int | None = None,
    ) -> dict[str, str]:
        """Create a rectangle, ellipse, or diamond with centered text and styles."""
        return {"id": "shape_1", "label_id": "lbl_1"}

    # 2. create_connector (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def create_connector(
        source_id: str | None = None,
        target_id: str | None = None,
        x: Coordinate | None = None,
        y: Coordinate | None = None,
        x2: Coordinate | None = None,
        y2: Coordinate | None = None,
        label: str = "",
        elbowed: bool = False,
        strokeColor: Color | None = None,
        strokeWidth: int | None = None,
        strokeStyle: StrokeStyle | None = None,
    ) -> dict[str, str]:
        """Create an arrow connecting two shapes by ID or between two coordinates."""
        return {"arrow_id": "arr_1"}

    # 3. add_text (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def add_text(
        x: Coordinate,
        y: Coordinate,
        text: str,
        font_size: int = 20,
        font_family: FontFamily = "excalifont",
        frame_id: str | None = None,
        color: Color | None = None,
    ) -> dict[str, str]:
        """Add standalone text to the canvas."""
        return {"text_id": "txt_1"}

    # 4. add_frame (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def add_frame(
        name: str,
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension,
    ) -> dict[str, str]:
        """Add a frame container for grouping and bounding diagram sections."""
        return {"frame_id": "frm_1"}

    # 5. update_element (CORE)
    @m.tool(annotations=IDEMPOTENT, output_schema=None if strip_output_schemas else ...)
    def update_element(
        element_id: str,
        x: Coordinate | None = None,
        y: Coordinate | None = None,
        width: Dimension | None = None,
        height: Dimension | None = None,
        label: str | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        font_size: int | None = None,
        frame_id: str | None = None,
    ) -> dict[str, str]:
        """Update position (move), size (resize), label, or styles of an existing element."""
        return {"element_id": element_id}

    # 6. delete (CORE)
    @m.tool(annotations=DESTRUCTIVE, output_schema=None if strip_output_schemas else ...)
    def delete(element_id: str) -> dict[str, str]:
        """Delete an element and its bound label; detaches surviving arrows."""
        return {"deleted_id": element_id}

    # 7. batch_mutate (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def batch_mutate(
        operations: list[BatchOp],
        auto_layout: bool = False,
    ) -> dict[str, Any]:
        """Atomically execute multiple creation, connection, edit, and delete operations in one transaction."""
        return {"executed": len(operations), "ref_map": {}}

    # 8. inspect_scene (CORE - Read-Only)
    @m.tool(annotations=READ_ONLY, output_schema=None if strip_output_schemas else ...)
    def inspect_scene(
        mode: Literal["summary", "describe", "element", "find"] = "summary",
        query: str | None = None,
        element_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Inspect the diagram: 'summary' (counts & metrics), 'describe' (spatial prose), 'element' (by ID), or 'find' (search)."""
        return {"mode": mode, "element_count": 10}

    # 9. auto_fix_layout (CORE)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def auto_fix_layout(
        dry_run: bool = False,
        repair_scope: Literal["all", "overlaps", "connectors", "containment", "text", "spacing"] = "all",
        aggressiveness: Literal["gentle", "balanced", "aggressive"] = "balanced",
        min_gap: float = 30.0,
    ) -> dict[str, Any]:
        """Diagnose (dry_run=True) and automatically repair layout defects, overlaps, and collisions."""
        return {"status": "ok", "fixed_count": 0}

    # 10. preview (CORE - Dedicated Read-Only Canvas Image)
    @m.tool(annotations=READ_ONLY)
    def preview(
        scale: float = 1.0,
        padding: int = 40,
        max_dimension: int = 1280,
    ) -> dict[str, str]:
        """Render an inline PNG preview of the canvas. Downscaled if exceeding max_dimension."""
        return {"preview": "data:image/png;base64,..."}

    # 11. undo (CORE)
    @m.tool(annotations=DESTRUCTIVE, output_schema=None if strip_output_schemas else ...)
    def undo() -> dict[str, str]:
        """Restore the canvas state before the most recent successful mutation."""
        return {"status": "undone"}

    # 12. clear (CORE)
    @m.tool(annotations=DESTRUCTIVE, output_schema=None if strip_output_schemas else ...)
    def clear() -> dict[str, str]:
        """Remove all elements and reset canvas."""
        return {"status": "cleared"}

    # --- ADVANCED TOOLS (FULL PROFILE ONLY - 6 TOOLS) ---

    # 13. generate_diagram (FULL)
    if typed_generator:
        @m.tool(annotations=DESTRUCTIVE, output_schema=None if strip_output_schemas else ...)
        def generate_diagram(
            format: Literal["mermaid", "architecture", "graph"],
            code: str | None = Field(default=None, description="Mermaid flowchart code or architecture shorthand prompt"),
            nodes: list[GraphNode] | None = Field(default=None, description="List of nodes for structured graph"),
            edges: list[GraphEdge] | None = Field(default=None, description="List of edges for structured graph"),
            clusters: list[GraphCluster] | None = Field(default=None, description="Optional cluster frames"),
            layout: Literal["layered", "horizontal", "vertical"] = "layered",
            direction: Literal["horizontal", "vertical"] = "horizontal",
            elbowed: bool = False,
        ) -> dict[str, Any]:
            """Generate diagram from DSL (Mermaid or architecture prompt) or structured graph specification."""
            return {"status": "generated", "nodes": 10, "edges": 12}
    else:
        @m.tool(annotations=DESTRUCTIVE, output_schema=None if strip_output_schemas else ...)
        def generate_diagram(
            format: Literal["mermaid", "architecture", "graph"],
            code: str | None = None,
            spec: dict[str, Any] | None = None,
            layout: str = "layered",
            direction: str = "horizontal",
        ) -> dict[str, Any]:
            """Generate diagram from DSL (Mermaid, architecture prompt) or structured graph dict."""
            return {"status": "generated"}

    # 14. scene_storage (FULL)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def scene_storage(
        action: Literal["save", "load", "list", "import", "export"],
        name: str | None = None,
        overwrite: bool = False,
        raw_data: str | None = None,
    ) -> dict[str, Any]:
        """Manage diagram storage: save to disk, load from disk, list saved scenes, import, or export raw document."""
        return {"action": action}

    # 15. export_png (FULL)
    @m.tool(annotations=MUTATING, output_schema=None if strip_output_schemas else ...)
    def export_png(
        name: str,
        scale: float = 1.0,
        padding: int = 40,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """Export high-resolution presentation PNG image file (up to 8192px) to disk."""
        return {"path": f"/exports/{name}.png"}

    # 16. manage_element_state (FULL)
    @m.tool(annotations=IDEMPOTENT, output_schema=None if strip_output_schemas else ...)
    def manage_element_state(
        element_ids: list[str],
        action: Literal["lock", "unlock", "group", "ungroup"],
        group_id: str | None = None,
    ) -> dict[str, Any]:
        """Lock or unlock elements against edits, or group/ungroup elements."""
        return {"action": action, "count": len(element_ids)}

    # 17. set_viewport (FULL)
    @m.tool(annotations=IDEMPOTENT, output_schema=None if strip_output_schemas else ...)
    def set_viewport(
        scroll_x: float | None = None,
        scroll_y: float | None = None,
        zoom: float | None = None,
        focus_element_ids: list[str] | None = None,
        padding: float = 50.0,
    ) -> dict[str, Any]:
        """Set canvas camera scroll offset, zoom level, or auto-focus framing on specific elements."""
        return {"zoom": zoom or 1.0}

    # 18. live_server (FULL)
    @m.tool(annotations=IDEMPOTENT, output_schema=None if strip_output_schemas else ...)
    def live_server(
        action: Literal["start", "stop", "status"],
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> dict[str, Any]:
        """Manage background browser-connected live canvas WebSocket synchronization server."""
        return {"status": "running"}

    return m


async def main():
    print("=" * 70)
    print("OPTION B PROTOTYPE MEASUREMENTS")
    print("=" * 70)

    # Full with Typed Generator (output schemas stripped)
    m_full_typed = build_option_b_server(typed_generator=True, strip_output_schemas=True)
    async with Client(m_full_typed) as c:
        tools = await c.list_tools()
        tools_wire = [t.model_dump(by_alias=True, exclude_none=True) for t in tools]
        ft_pretty = json.dumps({"tools": tools_wire}, indent=2)
        ft_compact = json.dumps({"tools": tools_wire}, separators=(',', ':'))
        t_ftp = tok(ft_pretty)
        t_ftc = tok(ft_compact)

    # Full with Untyped Generator (output schemas stripped)
    m_full_untyped = build_option_b_server(typed_generator=False, strip_output_schemas=True)
    async with Client(m_full_untyped) as c:
        tools_u = await c.list_tools()
        tools_u_wire = [t.model_dump(by_alias=True, exclude_none=True) for t in tools_u]
        fut_pretty = json.dumps({"tools": tools_u_wire}, indent=2)
        fut_compact = json.dumps({"tools": tools_u_wire}, separators=(',', ':'))
        t_futp = tok(fut_pretty)
        t_futc = tok(fut_compact)

    # Full with Typed Generator (output schemas retained)
    m_full_out = build_option_b_server(typed_generator=True, strip_output_schemas=False)
    async with Client(m_full_out) as c:
        tools_o = await c.list_tools()
        tools_o_wire = [t.model_dump(by_alias=True, exclude_none=True) for t in tools_o]
        fo_pretty = json.dumps({"tools": tools_o_wire}, indent=2)
        fo_compact = json.dumps({"tools": tools_o_wire}, separators=(',', ':'))
        t_fop = tok(fo_pretty)
        t_foc = tok(fo_compact)

    # Core Profile (First 12 tools)
    core_wire = tools_wire[:12]
    cp_pretty = json.dumps({"tools": core_wire}, indent=2)
    cp_compact = json.dumps({"tools": core_wire}, separators=(',', ':'))
    t_cp = tok(cp_pretty)
    t_cc = tok(cp_compact)

    print(f"\n1. Option B FULL (18 tools, Typed Generator, Output Schema Stripped):")
    print(f"   Compact JSON: {t_ftc['bytes']:,} B | {t_ftc['o200k']:,} tokens (o200k) | {t_ftc['cl100k']:,} tokens (cl100k)")
    print(f"   Pretty JSON:  {t_ftp['bytes']:,} B | {t_ftp['o200k']:,} tokens (o200k) | {t_ftp['cl100k']:,} tokens (cl100k)")

    print(f"\n2. Option B FULL (18 tools, Untyped Generator, Output Schema Stripped):")
    print(f"   Compact JSON: {t_futc['bytes']:,} B | {t_futc['o200k']:,} tokens (o200k) | {t_futc['cl100k']:,} tokens (cl100k)")
    print(f"   Pretty JSON:  {t_futp['bytes']:,} B | {t_futp['o200k']:,} tokens (o200k) | {t_futp['cl100k']:,} tokens (cl100k)")

    print(f"\n3. Option B FULL (18 tools, Typed Generator, Output Schema Retained):")
    print(f"   Compact JSON: {t_foc['bytes']:,} B | {t_foc['o200k']:,} tokens (o200k) | {t_foc['cl100k']:,} tokens (cl100k)")
    print(f"   Pretty JSON:  {t_fop['bytes']:,} B | {t_fop['o200k']:,} tokens (o200k) | {t_fop['cl100k']:,} tokens (cl100k)")

    print(f"\n4. Option B CORE (12 tools, Output Schema Stripped):")
    print(f"   Compact JSON: {t_cc['bytes']:,} B | {t_cc['o200k']:,} tokens (o200k) | {t_cc['cl100k']:,} tokens (cl100k)")
    print(f"   Pretty JSON:  {t_cp['bytes']:,} B | {t_cp['o200k']:,} tokens (o200k) | {t_cp['cl100k']:,} tokens (cl100k)")


if __name__ == "__main__":
    asyncio.run(main())
