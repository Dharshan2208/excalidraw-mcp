"""MCP adapters; each server owns an explicit scene service."""

import functools
from hashlib import sha256
import inspect
import json
from typing import Any, Literal

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from fastmcp.tools.base import Tool, ToolResult
from fastmcp.utilities.types import Image
from mcp.types import ContentBlock, EmbeddedResource, TextContent, TextResourceContents
from mcp.types import ToolAnnotations
from pydantic import AnyUrl

_orig_convert_result = Tool.convert_result


def _compact_json(data: Any) -> str:
    """Serialize data to minified JSON without redundant whitespace."""
    if hasattr(data, "model_dump"):
        data = data.model_dump(by_alias=True, exclude_none=True)
    return json.dumps(data, separators=(",", ":"))


def _custom_convert_result(self, raw_value: Any) -> ToolResult:
    """Return single compact JSON TextContent with no structuredContent."""
    if isinstance(raw_value, (ToolResult, Image, ContentBlock, EmbeddedResource)):
        return _orig_convert_result(self, raw_value)
    return ToolResult(
        content=[TextContent(type="text", text=_compact_json(raw_value))],
        structured_content=None,
    )


Tool.convert_result = _custom_convert_result


def _configure_tool_registration(mcp: FastMCP) -> None:
    """Shared mechanism to strip outputSchema from registered tools."""
    orig_tool = mcp.tool

    def custom_tool(name_or_fn=None, **kwargs):
        kwargs["output_schema"] = None
        return orig_tool(name_or_fn, **kwargs)

    mcp.tool = custom_tool

from excalidraw_mcp.contracts import (
    Aggressiveness,
    ArchitectureResult,
    Arrowhead,
    AutoFixLayoutResult,
    BatchOperation,
    BatchResult,
    Boolean,
    CodeBlockResult,
    CodeTheme,
    Color,
    ConnectResult,
    Coordinate,
    CreateResult,
    CreateShapeType,
    DeleteResult,
    DiagramFormat,
    DiagramGuideResult,
    DiagramResult,
    Dimension,
    Direction,
    DuplicateResult,
    ElementId,
    ElementResult,
    ElementStateAction,
    ElementSummary,
    ElementType,
    FillStyle,
    FindResult,
    FocusResult,
    FontSize,
    FontCategory,
    FontFamily,
    FontListResult,
    GraphCluster,
    GraphEdge,
    GraphNode,
    GraphResult,
    GroupResult,
    ImportResult,
    InspectMode,
    Label,
    LayoutType,
    LiveServerAction,
    LiveServerResult,
    LoadResult,
    LockResult,
    MoveResult,
    NonEmptyText,
    Offset,
    Opacity,
    PageLimit,
    PngExportResult,
    SvgExportResult,
    PreviewFormat,
    PreviewMaxDimension,
    PreviewPadding,
    PreviewScale,
    RepairScope,
    ResizeResult,
    ResourceResult,
    Roughness,
    Roundness,
    SaveResult,
    SavedScenesResult,
    SceneDescriptionResult,
    SceneName,
    ScenePage,
    SceneSummaryResult,
    ShapeType,
    ShareUrlResult,
    StatusResult,
    StorageAction,
    StorageFormat,
    StorageResult,
    StrokeStyle,
    StrokeWidth,
    UndoResult,
    UnlockResult,
    UngroupResult,
    UpdateResult,
    ViewportResult,
)
from excalidraw_mcp.config import configured_toolset
from excalidraw_mcp.document import MIME_TYPE
from excalidraw_mcp.service import SceneService

MUTATING = ToolAnnotations(
    destructiveHint=False, idempotentHint=False, openWorldHint=False
)
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)


def _style_kwargs(
    strokeColor: str | None = None,
    backgroundColor: str | None = None,
    fillStyle: str | None = None,
    strokeWidth: int | None = None,
    strokeStyle: str | None = None,
    opacity: int | None = None,
    roughness: int | None = None,
    roundness: str | None = None,
    font_family: Any = None,
    font_size: int | None = None,
    startArrowhead: str | None = None,
    endArrowhead: str | None = None,
) -> dict:
    """Collect non-None style keyword arguments into a dict."""
    return {k: v for k, v in locals().items() if v is not None}


def get_server_version() -> str:
    """Return dynamically detected package version with safe fallback."""
    try:
        from importlib.metadata import version
        return version("exca-mcp")
    except Exception:
        return "0.3.0"


def create_server(
    service: SceneService | None = None,
    toolset: str | None = None,
    session_id: str | None = None,
) -> FastMCP:
    if service is None:
        service = SceneService(session_id=session_id)
    elif session_id is not None:
        service = service.for_session(session_id)
    active_toolset = (
        toolset if toolset is not None else configured_toolset()
    ).strip().lower()
    is_full = active_toolset == "full"
    instructions = (
        "Create and edit Excalidraw diagrams. Use create_shape, create_connector, add_text, "
        "and add_frame for primitives, or batch_mutate for atomic updates. Use inspect_scene to query "
        "elements and metrics. Use auto_fix_layout to repair defects, and preview to inspect visuals."
    )
    mcp = FastMCP("Excalidraw MCP", instructions=instructions)
    _configure_tool_registration(mcp)

    def invoke(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=MUTATING)
    def create_shape(
        type: CreateShapeType,
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension | None = None,
        label: Label = "",
        frame_id: ElementId | None = None,
        roundness: Roundness | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
    ) -> dict[str, Any]:
        """Create a shape (rectangle, ellipse, diamond) with optional label and styling."""
        shape_type = "ellipse" if type == "circle" else type
        height = h if h is not None else w
        style = _style_kwargs(
            strokeColor=strokeColor,
            backgroundColor=backgroundColor,
            fillStyle=fillStyle,
            strokeWidth=strokeWidth,
            strokeStyle=strokeStyle,
            opacity=opacity,
            roughness=roughness,
            roundness=roundness,
            font_family=font_family,
            font_size=font_size,
        )
        res = invoke(
            service.add_shape, shape_type, x, y, w, height, label, frame_id=frame_id, **style
        )
        res_dict = dict(res)
        primary_id = res_dict.get("rectangle_id") or res_dict.get("circle_id") or res_dict.get("diamond_id")
        if primary_id:
            res_dict["id"] = primary_id
            res_dict["element_id"] = primary_id
        return res_dict

    @mcp.tool(annotations=MUTATING)
    def create_connector(
        source_id: ElementId | None = None,
        target_id: ElementId | None = None,
        x: Coordinate | None = None,
        y: Coordinate | None = None,
        x2: Coordinate | None = None,
        y2: Coordinate | None = None,
        label: Label = "",
        elbowed: Boolean = False,
        startArrowhead: Arrowhead | None = None,
        endArrowhead: Arrowhead | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        strokeStyle: StrokeStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        roughness: Roughness | None = None,
        opacity: Opacity | None = None,
        roundness: Roundness | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
    ) -> dict[str, Any]:
        """Create a connector arrow between coordinates or bound shape elements."""
        style = _style_kwargs(
            strokeColor=strokeColor,
            backgroundColor=backgroundColor,
            strokeWidth=strokeWidth,
            strokeStyle=strokeStyle,
            opacity=opacity,
            roughness=roughness,
            roundness=roundness,
            font_family=font_family,
            font_size=font_size,
            startArrowhead=startArrowhead,
            endArrowhead=endArrowhead,
        )
        if source_id and target_id:
            res = invoke(service.connect, source_id, target_id, label, elbowed=elbowed, **style)
        elif x is not None and y is not None and x2 is not None and y2 is not None:
            res = invoke(service.add_arrow, x, y, x2, y2, label, elbowed=elbowed, **style)
        else:
            raise ToolError(
                "create_connector requires either both source_id and target_id, or coordinate points (x, y, x2, y2)."
            )
        res_dict = dict(res)
        if "arrow_id" in res_dict:
            res_dict["id"] = res_dict["arrow_id"]
            res_dict["element_id"] = res_dict["arrow_id"]
        return res_dict

    @mcp.tool(annotations=MUTATING)
    def add_frame(
        name: Label,
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension,
        element_ids: list[ElementId] | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> CreateResult:
        """Create a frame container, optionally enclosing existing elements."""
        style = _style_kwargs(
            strokeColor=strokeColor,
            backgroundColor=backgroundColor,
            fillStyle=fillStyle,
            strokeWidth=strokeWidth,
            strokeStyle=strokeStyle,
            opacity=opacity,
            roughness=roughness,
        )
        return invoke(
            service.add_frame,
            name,
            x,
            y,
            w,
            h,
            element_ids=element_ids,
            **style,
        )

    @mcp.tool(
        annotations=ToolAnnotations(
            destructiveHint=True, idempotentHint=True, openWorldHint=False
        ),
    )
    def clear() -> StatusResult:
        """Clear all elements and state from the active scene."""
        return invoke(service.clear)

    @mcp.tool(
        annotations=ToolAnnotations(
            destructiveHint=True, idempotentHint=False, openWorldHint=False
        ),
    )
    def delete(element_id: ElementId) -> DeleteResult:
        """Delete an element and detach surviving connectors."""
        return invoke(service.delete, element_id)

    @mcp.tool(annotations=READ_ONLY)
    def inspect_scene(
        mode: InspectMode = "summary",
        element_id: ElementId | None = None,
        query: str | None = None,
        type: ElementType | None = None,
        frame_id: ElementId | None = None,
        connected_to: ElementId | None = None,
        include_bound_labels: bool = False,
        limit: PageLimit = 50,
        offset: Offset = 0,
        detailed: Boolean = True,
        include_raw: Boolean = False,
        resource_uri: str | None = None,
    ) -> dict[str, Any]:
        """Query scene metrics, spatial descriptions, elements, viewport, or server status."""
        if mode == "summary":
            return invoke(service.get_scene_summary)
        elif mode == "describe":
            res = invoke(service.describe_scene, detailed=detailed)
            if not include_raw:
                return {"summary": res["summary"]}
            return res
        elif mode == "elements":
            return invoke(service.get_scene, offset, limit)
        elif mode == "element":
            if not element_id:
                raise ToolError("inspect_scene(mode='element') requires element_id parameter.")
            return invoke(service.get_element, element_id)
        elif mode == "find":
            return invoke(
                service.find_elements,
                query=query,
                type=type,
                frame_id=frame_id,
                element_id=element_id,
                connected_to=connected_to,
                include_bound_labels=include_bound_labels,
                limit=limit,
            )
        elif mode == "viewport":
            return invoke(service.get_viewport)
        elif mode == "live_server":
            return invoke(service.get_live_server_status)
        elif mode == "resource":
            if not resource_uri:
                raise ToolError("inspect_scene(mode='resource') requires resource_uri parameter.")
            return invoke(
                service.get_resource,
                uri=resource_uri,
                resource_type=None,
                identifier=element_id,
            )
        else:
            raise ToolError(f"Unknown inspect mode: '{mode}'")

    @mcp.tool(annotations=MUTATING)
    def add_text(
        x: Coordinate,
        y: Coordinate,
        content: NonEmptyText,
        font_size: FontSize = 20,
        font_family: FontFamily | None = None,
        frame_id: ElementId | None = None,
        strokeColor: Color | None = None,
        opacity: Opacity | None = None,
    ) -> CreateResult:
        """Add standalone text element to the scene."""
        return invoke(
            service.add_text,
            x,
            y,
            content,
            font_size,
            font_family=font_family,
            frame_id=frame_id,
            **_style_kwargs(strokeColor=strokeColor, opacity=opacity),
        )

    @mcp.tool(
        annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
    )
    def update_element(
        element_id: ElementId,
        label: Label | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        roundness: Roundness | None = None,
        frame_id: ElementId | None = None,
        elbowed: Boolean | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
        x: Coordinate | None = None,
        y: Coordinate | None = None,
        width: Dimension | None = None,
        height: Dimension | None = None,
    ) -> dict[str, Any]:
        """Update element position, size, label, or visual styling."""
        res: dict[str, Any] = {"status": "updated", "element_id": element_id}
        if width is not None or height is not None:
            if width is None or height is None:
                el = invoke(service.get_element, element_id)["element"]
                w_val = float(width if width is not None else el.get("width", 100))
                h_val = float(height if height is not None else el.get("height", 100))
            else:
                w_val, h_val = width, height
            res.update(invoke(service.resize, element_id, w_val, h_val))
        if x is not None or y is not None:
            if x is None or y is None:
                el = invoke(service.get_element, element_id)["element"]
                x_val = float(x if x is not None else el.get("x", 0))
                y_val = float(y if y is not None else el.get("y", 0))
            else:
                x_val, y_val = x, y
            res.update(invoke(service.move, element_id, x_val, y_val))
        has_updates = any(
            v is not None
            for v in (
                label,
                strokeColor,
                backgroundColor,
                fillStyle,
                strokeWidth,
                strokeStyle,
                opacity,
                roughness,
                roundness,
                frame_id,
                elbowed,
                font_family,
                font_size,
            )
        )
        if has_updates or (width is None and height is None and x is None and y is None):
            res.update(
                invoke(
                    service.update_element,
                    element_id,
                    label,
                    strokeColor,
                    backgroundColor,
                    fillStyle,
                    strokeWidth,
                    strokeStyle,
                    opacity,
                    roughness,
                    roundness=roundness,
                    frame_id=frame_id,
                    elbowed=elbowed,
                    font_family=font_family,
                    font_size=font_size,
                )
            )
        return res

    @mcp.tool(annotations=MUTATING)
    def batch_mutate(
        operations: list[dict[str, Any]],
    ) -> BatchResult:
        """Atomically execute a batch of canvas mutations in a single revision step."""
        return invoke(
            service.batch_mutate,
            [op.model_dump(exclude_none=True) if hasattr(op, "model_dump") else op for op in operations],
        )

    @mcp.tool(annotations=MUTATING)
    def auto_fix_layout(
        name: SceneName | None = None,
        dry_run: Boolean = False,
        repair_scope: RepairScope = "all",
        aggressiveness: Aggressiveness = "balanced",
        min_gap: float = 30.0,
        verbose: Boolean = False,
        ctx: Context | None = None,
    ) -> dict[str, Any]:
        """Diagnose and automatically repair layout defects with rollback safety."""
        def sync_progress(phase: int, total: int, msg: str):
            if ctx:
                try:
                    import anyio.from_thread
                    anyio.from_thread.run(ctx.report_progress, phase, total, msg)
                except Exception:
                    try:
                        import asyncio
                        loop = asyncio.get_running_loop()
                        loop.create_task(ctx.report_progress(phase, total, msg))
                    except Exception:
                        pass

        result = invoke(
            service.auto_fix_layout,
            name=name,
            dry_run=dry_run,
            repair_scope=repair_scope,
            aggressiveness=aggressiveness,
            min_gap=min_gap,
            progress_callback=sync_progress,
        )
        if verbose:
            return result
        res = dict(result)
        init_issues = res.get("initial_issues", [])
        unres_issues = res.get("unresolved_issues", [])
        fin_issues = res.get("final_issues", [])
        applied = res.pop("applied_changes", [])
        res["initial_issue_count"] = len(init_issues)
        res["unresolved_issue_count"] = len(unres_issues)
        res["issues_truncated"] = len(init_issues) > 5 or len(unres_issues) > 5
        res["initial_issues"] = init_issues[:5]
        res["unresolved_issues"] = unres_issues[:5]
        if "final_issues" in res:
            res["final_issues"] = fin_issues[:5]
        res["applied_change_count"] = len(applied)
        if "changed_element_ids" not in res:
            res["changed_element_ids"] = []
        return res

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
    )
    def undo() -> UndoResult:
        """Restore the scene before the most recent successful mutation."""
        return invoke(service.undo)

    @mcp.resource("excalidraw://active/scene.json", mime_type=MIME_TYPE)
    def active_scene_json_resource() -> str:
        """Read the current in-memory active canvas scene as native Excalidraw JSON."""
        doc, _ = service.state.snapshot()
        import json
        return json.dumps(doc, separators=(",", ":"))

    @mcp.resource("excalidraw://active", mime_type=MIME_TYPE)
    def active_scene_resource() -> str:
        """Read the current in-memory active canvas scene."""
        doc, _ = service.state.snapshot()
        import json
        return json.dumps(doc, separators=(",", ":"))

    @mcp.resource("excalidraw://scenes/{name}.excalidraw", mime_type=MIME_TYPE)
    def saved_scene_resource(name: SceneName) -> str:
        """Read a validated saved scene without changing the active scene."""
        return invoke(service.read_saved_scene, name)

    @mcp.resource("excalidraw://fonts", mime_type="application/json")
    def fonts_resource() -> str:
        """Read discoverable fonts and semantic categories available on the server."""
        import json
        return json.dumps(invoke(service.list_fonts))

    @mcp.resource("excalidraw://guide/{topic}", mime_type="text/markdown")
    def diagram_guide_resource(topic: str) -> str:
        """Read diagram guidelines for layout, spacing, colors, typography, and arrows."""
        res = invoke(service.read_diagram_guide, topic=topic)
        guide = res.get("guide", {})
        if isinstance(guide, dict):
            lines = [f"# {guide.get('title', topic.title())}\n"]
            if "principles" in guide and isinstance(guide["principles"], list):
                lines.append("## Principles\n")
                for p in guide["principles"]:
                    lines.append(f"- {p}")
                lines.append("")
            if "recommendations" in guide and isinstance(guide["recommendations"], dict):
                lines.append("## Recommendations\n")
                for k, v in guide["recommendations"].items():
                    lines.append(f"- **{k}**: {v}")
                lines.append("")
            return "\n".join(lines).strip()
        return str(guide)

    @mcp.tool(annotations=READ_ONLY)
    def preview(
        scale: PreviewScale = 1.0,
        padding: PreviewPadding = 40,
        background: Boolean = True,
        max_dimension: PreviewMaxDimension = 1568,
        format: PreviewFormat = "png",
    ) -> Image:
        """Render an inline image preview of the active Excalidraw canvas."""
        data = invoke(
            service.preview,
            scale=scale,
            padding=padding,
            background=background,
        )
        fmt = format.lower()
        if max_dimension is not None and max_dimension > 0:
            import io
            from PIL import Image as PILImage

            with PILImage.open(io.BytesIO(data)) as im:
                w, h = im.size
                needs_resize = max(w, h) > max_dimension
                needs_format_change = fmt == "jpeg"

                if needs_resize or needs_format_change:
                    if needs_resize:
                        ratio = max_dimension / max(w, h)
                        new_w = max(1, int(round(w * ratio)))
                        new_h = max(1, int(round(h * ratio)))
                        im = im.resize((new_w, new_h), PILImage.Resampling.LANCZOS)

                    out_buf = io.BytesIO()
                    if fmt == "jpeg":
                        if im.mode in ("RGBA", "LA", "P"):
                            rgb_im = PILImage.new("RGB", im.size, (255, 255, 255))
                            if im.mode == "P":
                                im = im.convert("RGBA")
                            rgb_im.paste(
                                im, mask=im.split()[-1] if "A" in im.mode else None
                            )
                            rgb_im.save(out_buf, format="JPEG", quality=85)
                        else:
                            im.save(out_buf, format="JPEG", quality=85)
                        data = out_buf.getvalue()
                    elif needs_resize:
                        im.save(out_buf, format="PNG")
                        data = out_buf.getvalue()

        return Image(data=data, format=fmt)

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
        )
        def scene_storage(
            action: StorageAction = "save",
            name: SceneName | None = None,
            overwrite: Boolean = False,
            data: str | None = None,
            mode: Literal["replace", "merge"] = "replace",
            offset_x: Coordinate = 0.0,
            offset_y: Coordinate = 0.0,
            format: StorageFormat = "excalidraw",
            directory: str | None = None,
        ) -> Any:
            """Save, load, list, export, or import diagram scenes."""
            if action == "save":
                if not name:
                    raise ToolError("scene_storage(action='save') requires name parameter.")
                if format == "obsidian":
                    return invoke(service.export_obsidian, name, directory=directory, overwrite=overwrite)
                return invoke(service.save, name, overwrite=overwrite)
            elif action == "load":
                if not name:
                    raise ToolError("scene_storage(action='load') requires name parameter.")
                return invoke(service.load, name)
            elif action == "list":
                return invoke(service.list_saved_scenes)
            elif action == "export":
                if format == "obsidian":
                    payload = invoke(service.export_scene, format="obsidian")
                    snapshot_id = sha256(payload.encode("utf-8")).hexdigest()
                    return EmbeddedResource(
                        type="resource",
                        resource=TextResourceContents(
                            uri=AnyUrl(f"excalidraw://export/{snapshot_id}/scene.excalidraw.md"),
                            mimeType="text/markdown",
                            text=payload,
                        ),
                    )
                payload = invoke(service.export_scene)
                snapshot_id = sha256(payload.encode("utf-8")).hexdigest()
                return EmbeddedResource(
                    type="resource",
                    resource=TextResourceContents(
                        uri=AnyUrl(f"excalidraw://export/{snapshot_id}/scene.excalidraw"),
                        mimeType=MIME_TYPE,
                        text=payload,
                    ),
                )
            elif action == "import":
                if not data:
                    raise ToolError("scene_storage(action='import') requires data parameter.")
                return invoke(
                    service.import_scene,
                    data=data,
                    mode=mode,
                    offset_x=offset_x,
                    offset_y=offset_y,
                )
            elif action == "share_url":
                return invoke(service.export_to_excalidraw_url, name=name)
            else:
                raise ToolError(f"Unsupported storage action: {action}")

        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=False, openWorldHint=True),
        )
        def export_png(
            name: SceneName,
            directory: str | None = None,
            scale: PreviewScale = 1.0,
            padding: PreviewPadding = 40,
            background: Boolean = True,
            overwrite: Boolean = False,
        ) -> PngExportResult:
            """Export active scene to a PNG image file."""
            return invoke(
                service.export_png,
                name=name,
                directory=directory,
                scale=scale,
                padding=padding,
                background=background,
                overwrite=overwrite,
            )

        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=False, openWorldHint=True),
        )
        def export_svg(
            name: SceneName,
            directory: str | None = None,
            padding: PreviewPadding = 40,
            background: Boolean = True,
            overwrite: Boolean = False,
        ) -> SvgExportResult:
            """Export active scene to a standalone vector SVG file."""
            return invoke(
                service.export_svg,
                name=name,
                directory=directory,
                padding=padding,
                background=background,
                overwrite=overwrite,
            )

        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
        )
        def generate_diagram(
            format: DiagramFormat = "mermaid",
            mermaid_code: str | None = None,
            prompt: str | None = None,
            nodes: list[GraphNode] | None = None,
            edges: list[GraphEdge] | None = None,
            clusters: list[GraphCluster] | None = None,
            layout: LayoutType = "layered",
            direction: Direction | None = None,
            elbowed: Boolean = False,
            roundness: Roundness | None = None,
            font_family: FontFamily | None = None,
            font_size: FontSize | None = None,
            cycle_fallback: Boolean = False,
            expected_revision: int | None = None,
            strokeColor: Color | None = None,
            backgroundColor: Color | None = None,
            fillStyle: FillStyle | None = None,
            strokeWidth: StrokeWidth | None = None,
            strokeStyle: StrokeStyle | None = None,
            opacity: Opacity | None = None,
            roughness: Roughness | None = None,
        ) -> DiagramResult:
            """Generate diagrams from Mermaid syntax, architecture text prompts, or graphs."""
            if format == "mermaid":
                if not mermaid_code or not mermaid_code.strip():
                    raise ToolError("generate_diagram(format='mermaid') requires non-empty mermaid_code parameter.")
                return invoke(
                    service.draw_mermaid,
                    mermaid_code=mermaid_code,
                    direction=direction,
                    layout=layout,
                    elbowed=elbowed,
                    roundness=roundness,
                )
            elif format == "architecture":
                if not prompt or not prompt.strip():
                    raise ToolError("generate_diagram(format='architecture') requires non-empty prompt parameter.")
                style = _style_kwargs(
                    strokeColor=strokeColor,
                    backgroundColor=backgroundColor,
                    fillStyle=fillStyle,
                    strokeWidth=strokeWidth,
                    strokeStyle=strokeStyle,
                    opacity=opacity,
                    roughness=roughness,
                    font_family=font_family,
                    font_size=font_size,
                )
                return invoke(service.draw_architecture, prompt, **style)
            elif format == "graph":
                if nodes is None or edges is None:
                    raise ToolError("generate_diagram(format='graph') requires nodes and edges parameters.")
                return invoke(
                    service.draw_graph,
                    [node.model_dump() if hasattr(node, "model_dump") else node for node in nodes],
                    [edge.model_dump() if hasattr(edge, "model_dump") else edge for edge in edges],
                    clusters=[cluster.model_dump() if hasattr(cluster, "model_dump") else cluster for cluster in clusters]
                    if clusters
                    else None,
                    layout=layout,
                    direction=direction or "horizontal",
                    elbowed=elbowed,
                    roundness=roundness,
                    font_family=font_family,
                    font_size=font_size,
                    cycle_fallback=cycle_fallback,
                    expected_revision=expected_revision,
                )
            else:
                raise ToolError(f"Unsupported diagram format: {format}")

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
        )
        def manage_element_state(
            element_ids: list[ElementId] | None = None,
            action: ElementStateAction = "lock",
            group_id: str | None = None,
            offset_x: Coordinate = 20.0,
            offset_y: Coordinate = 20.0,
        ) -> Any:
            """Lock, unlock, group, ungroup, or duplicate canvas elements."""
            if action == "lock":
                return invoke(service.set_element_locked, element_ids or [], locked=True)
            elif action == "unlock":
                return invoke(service.set_element_locked, element_ids or [], locked=False)
            elif action in ("group", "ungroup"):
                return invoke(service.manage_groups, element_ids=element_ids, group_id=group_id, action=action)
            elif action == "duplicate":
                if not element_ids:
                    raise ToolError("manage_element_state(action='duplicate') requires element_ids parameter.")
                return invoke(service.duplicate_elements, element_ids=element_ids, offset_x=offset_x, offset_y=offset_y)
            else:
                raise ToolError(f"Unsupported element action: {action}")

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
        )
        def set_viewport(
            scroll_x: Coordinate | None = None,
            scroll_y: Coordinate | None = None,
            zoom: float | None = None,
            background_color: Color | None = None,
            focus_element_ids: list[ElementId] | None = None,
            padding: PreviewPadding = 50,
        ) -> ViewportResult | FocusResult:
            """Configure viewport scroll, zoom, background color, or focus on elements."""
            return invoke(
                service.set_viewport,
                scroll_x=scroll_x,
                scroll_y=scroll_y,
                zoom=zoom,
                background_color=background_color,
                focus_element_ids=focus_element_ids,
                padding=padding,
            )

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=False, openWorldHint=True),
        )
        def export_to_excalidraw_url(name: SceneName | None = None) -> ShareUrlResult:
            """Publish scene to excalidraw.com and return a shareable URL."""
            return invoke(service.export_to_excalidraw_url, name=name)

    if is_full:
        @mcp.tool(annotations=READ_ONLY)
        def read_diagram_guide(topic: str | None = None) -> DiagramGuideResult:
            """Read design guidelines for layout, typography, colors, and readability."""
            return invoke(service.read_diagram_guide, topic=topic)

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=True),
        )
        def live_server(
            action: LiveServerAction = "start",
            host: str = "127.0.0.1",
            port: int = 8080,
        ) -> LiveServerResult:
            """Start or stop the background browser live canvas synchronization server."""
            if action == "start":
                return invoke(service.start_live_server, host=host, port=port)
            elif action == "stop":
                return invoke(service.stop_live_server)
            else:
                raise ToolError(f"Unsupported live_server action: {action}")

    @mcp.resource("excalidraw://capabilities", mime_type="application/json")
    def capabilities_resource() -> str:
        """Read active server capabilities, toolset mode, and configuration metadata."""
        import json
        from .config import scene_directory, max_elements

        info = {
            "active_toolset": active_toolset,
            "session_id": service.session_id,
            "active_sessions": service.list_sessions(),
            "available_toolsets": ["core", "full"],
            "server_version": get_server_version(),
            # Measured schema savings: core (27 tools / ~7,940 tokens) vs full (43 tools / ~14,376 tokens) -> ~45.2% token savings
            "tool_count": 21 if is_full else 12,
            "capabilities": {
                "generators": ["mermaid", "architecture_dsl"]
                + (["sugiyama_graph"] if is_full else []),
                "export": ["png", "svg", "excalidraw_json", "obsidian_markdown"],
                "repair": "5-phase topological auto_fix_layout with rollback",
                "full_only_features": [
                    "scene_storage",
                    "export_png",
                    "export_svg",
                    "generate_diagram",
                    "manage_element_state",
                    "set_viewport",
                    "live_server",
                    "export_to_excalidraw_url",
                    "read_diagram_guide",
                ],
            },
            "config": {
                "scene_dir": str(scene_directory()),
                "max_elements": max_elements(),
            },
            "upgrade_instructions": "To enable advanced tools, set environment variable EXCALIDRAW_TOOLSET=full.",
        }
        return json.dumps(info, indent=2)

    # Register agent skills discovery index, individual skills, and task prompts
    from .skills import register_skills_mcp

    register_skills_mcp(mcp)

    return mcp


mcp = create_server()


def main(argv: list[str] | None = None) -> None:
    """Run the installed stdio MCP server or CLI subcommands."""
    import sys

    args = sys.argv[1:] if argv is None else argv

    if args and args[0] == "install-skills":
        from .installer import run_install_skills_cli

        sys.exit(run_install_skills_cli(args[1:]))

    mcp.run()


def run():
    """Run the installed stdio MCP server."""
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
