"""MCP adapters; each server owns an explicit scene service."""

from hashlib import sha256
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.utilities.types import Image
from mcp.types import EmbeddedResource, TextResourceContents
from mcp.types import ToolAnnotations

from excalidraw_mcp.contracts import (
    Aggressiveness,
    ArchitectureResult,
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
    DeleteResult,
    DiagramGuideResult,
    Dimension,
    Direction,
    DuplicateResult,
    ElementId,
    ElementResult,
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
    Label,
    LayoutType,
    LiveServerResult,
    LoadResult,
    LockResult,
    MoveResult,
    NonEmptyText,
    Offset,
    Opacity,
    PageLimit,
    PngExportResult,
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
) -> dict:
    """Collect non-None style keyword arguments into a dict."""
    return {k: v for k, v in locals().items() if v is not None}


def create_server(
    service: SceneService | None = None,
    toolset: str | None = None,
) -> FastMCP:
    service = service if service is not None else SceneService()
    active_toolset = (
        toolset if toolset is not None else configured_toolset()
    ).strip().lower()
    is_full = active_toolset == "full"
    mcp = FastMCP("Excalidraw MCP")

    def invoke(operation, *args, **kwargs):
        try:
            return operation(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def add_rectangle(
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension,
        label: Label = "",
        roundness: Roundness | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        frame_id: ElementId | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> CreateResult:
        """Add a rectangle to the scene.

        Style parameters are optional — when omitted, Excalidraw defaults are used.
        """
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
        return invoke(
            service.add_shape, "rectangle", x, y, w, h, label, frame_id=frame_id, **style
        )

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def add_circle(
        x: Coordinate,
        y: Coordinate,
        size: Dimension,
        label: Label = "",
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        frame_id: ElementId | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> CreateResult:
        """Add a circle (ellipse) to the scene."""
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
        return invoke(
            service.add_shape, "ellipse", x, y, size, size, label, frame_id=frame_id, **style
        )

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def add_diamond(
        x: Coordinate,
        y: Coordinate,
        w: Dimension,
        h: Dimension,
        label: Label = "",
        roundness: Roundness | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        frame_id: ElementId | None = None,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> CreateResult:
        """Add a diamond to the scene."""
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
        return invoke(
            service.add_shape, "diamond", x, y, w, h, label, frame_id=frame_id, **style
        )

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def add_arrow(
        x: Coordinate,
        y: Coordinate,
        x2: Coordinate,
        y2: Coordinate,
        label: Label = "",
        elbowed: Boolean = False,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        strokeColor: Color | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> CreateResult:
        """Add an arrow between two points.

        Optionally add bound text near the arrow midpoint.
        """
        style = _style_kwargs(
            strokeColor=strokeColor,
            strokeWidth=strokeWidth,
            strokeStyle=strokeStyle,
            opacity=opacity,
            roughness=roughness,
            font_family=font_family,
            font_size=font_size,
        )
        return invoke(service.add_arrow, x, y, x2, y2, label, elbowed=elbowed, **style)

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
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
        """Add a frame (boundary container) to the scene.

        Optionally assign existing elements to this frame using `element_ids`.
        """
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
        run_in_thread=False,
    )
    def clear() -> StatusResult:
        """Remove all elements, app state and files from the scene."""
        return invoke(service.clear)

    @mcp.tool(
        annotations=ToolAnnotations(
            destructiveHint=True, idempotentHint=False, openWorldHint=False
        ),
        run_in_thread=False,
    )
    def delete(element_id: ElementId) -> DeleteResult:
        """Delete an element and its owned label; detach surviving connectors."""
        return invoke(service.delete, element_id)

    @mcp.tool(
        annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
        run_in_thread=False,
    )
    def move(element_id: ElementId, x: Coordinate, y: Coordinate) -> MoveResult:
        """Move an element and its label. Shape connectors follow; directly moved arrows detach."""
        return invoke(service.move, element_id, x, y)

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True),
        run_in_thread=False,
    )
    def save(name: SceneName, overwrite: Boolean = False) -> SaveResult:
        """Save a consistent snapshot. Set overwrite=true to replace an existing file."""
        return invoke(service.save, name, overwrite=overwrite)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def get_scene(offset: Offset = 0, limit: PageLimit = 50) -> ScenePage:
        """List active elements with pagination and the current revision."""
        return invoke(service.get_scene, offset, limit)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def get_element(element_id: ElementId) -> ElementResult:
        """Return one active element by ID."""
        return invoke(service.get_element, element_id)

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=True),
            run_in_thread=False,
        )
        def list_saved_scenes() -> SavedScenesResult:
            """List scene names available in the configured storage directory."""
            return invoke(service.list_saved_scenes)

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
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
        """Add standalone text and return its element ID. font_family can be 'excalifont', 'sans-serif', 'monospace', 'comic-shanns', or an Excalidraw font number (1=Excalifont, 2=sans-serif, 3=monospace, 4=comic-shanns)."""
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
        run_in_thread=False,
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
    ) -> UpdateResult:
        """Update a label, font, and/or styles. An empty label removes an existing label."""
        return invoke(
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

    @mcp.tool(
        annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
        run_in_thread=False,
    )
    def resize(
        element_id: ElementId, width: Dimension, height: Dimension
    ) -> ResizeResult:
        """Resize a shape and recenter its label."""
        return invoke(service.resize, element_id, width, height)

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def connect(
        source_id: ElementId,
        target_id: ElementId,
        label: Label = "",
        elbowed: Boolean = False,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
        strokeColor: Color | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
    ) -> ConnectResult:
        """Connect two existing shapes by ID with a bound arrow."""
        return invoke(
            service.connect,
            source_id,
            target_id,
            label,
            elbowed=elbowed,
            **_style_kwargs(
                strokeColor=strokeColor,
                strokeWidth=strokeWidth,
                strokeStyle=strokeStyle,
                opacity=opacity,
                roughness=roughness,
                font_family=font_family,
                font_size=font_size,
            ),
        )

    if is_full:
        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def find_elements(
            query: str | None = None,
            type: ElementType | None = None,
            frame_id: ElementId | None = None,
            element_id: ElementId | None = None,
            connected_to: ElementId | None = None,
            include_bound_labels: bool = False,
            limit: PageLimit = 50,
        ) -> FindResult:
            """Find active elements matching query string, type, frame, or connection criteria."""
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

        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def batch_mutate(
            operations: list[BatchOperation],
        ) -> BatchResult:
            """Atomically execute a batch of creation, editing, and deletion operations."""
            return invoke(
                service.batch_mutate,
                [op.model_dump(exclude_unset=False) for op in operations],
            )

    @mcp.tool(annotations=MUTATING, run_in_thread=False)
    def auto_fix_layout(
        name: SceneName | None = None,
        dry_run: Boolean = False,
        repair_scope: RepairScope = "all",
        aggressiveness: Aggressiveness = "balanced",
        min_gap: float = 30.0,
    ) -> AutoFixLayoutResult:
        """Diagnose, plan, and automatically repair layout defects (overlaps, text clipping, containment, routing, spacing) with rollback safety."""
        return invoke(
            service.auto_fix_layout,
            name=name,
            dry_run=dry_run,
            repair_scope=repair_scope,
            aggressiveness=aggressiveness,
            min_gap=min_gap,
        )

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
        run_in_thread=False,
    )
    def undo() -> UndoResult:
        """Restore the scene before the most recent successful mutation."""
        return invoke(service.undo)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def export_scene() -> EmbeddedResource:
        """Return an embedded .excalidraw document for the client to save/import. No file is written."""
        payload = invoke(service.export_scene)
        snapshot_id = sha256(payload.encode("utf-8")).hexdigest()
        return EmbeddedResource(
            type="resource",
            resource=TextResourceContents(
                uri=f"excalidraw://export/{snapshot_id}/scene.excalidraw",
                mimeType=MIME_TYPE,
                text=payload,
            ),
        )

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=True),
        run_in_thread=False,
    )
    def load(name: SceneName) -> LoadResult:
        """Replace the scene with a saved document; concurrent changes cause a retry error."""
        return invoke(service.load, name)

    @mcp.resource("excalidraw://scenes/{name}.excalidraw", mime_type=MIME_TYPE)
    def saved_scene_resource(name: SceneName) -> str:
        """Read a validated saved scene without changing the active scene."""
        return invoke(service.read_saved_scene, name)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def preview(
        scale: PreviewScale = 1.0,
        padding: PreviewPadding = 40,
        background: Boolean = True,
    ) -> Image:
        """Render an inline PNG image preview of the active Excalidraw canvas."""
        data = invoke(
            service.preview,
            scale=scale,
            padding=padding,
            background=background,
        )
        return Image(data=data, format="png")

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=False, openWorldHint=True),
        run_in_thread=False,
    )
    def export_png(
        name: SceneName,
        directory: str | None = None,
        scale: PreviewScale = 1.0,
        padding: PreviewPadding = 40,
        background: Boolean = True,
        overwrite: Boolean = False,
    ) -> PngExportResult:
        """Export the active scene to a PNG image file in a project or configured directory."""
        return invoke(
            service.export_png,
            name=name,
            directory=directory,
            scale=scale,
            padding=padding,
            background=background,
            overwrite=overwrite,
        )

    if is_full:
        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def add_code_block(
            code: str,
            language: str = "python",
            x: Coordinate = 0,
            y: Coordinate = 0,
            title: str | None = None,
            theme: CodeTheme = "dark",
            font_size: FontSize = 14,
            font_family: str | None = "monospace",
            line_numbers: Boolean = True,
            w: Dimension | None = None,
            h: Dimension | None = None,
            frame_id: ElementId | None = None,
        ) -> CodeBlockResult:
            """Add a syntax-highlighted code block with window controls and line numbers."""
            return invoke(
                service.add_code_block,
                code=code,
                language=language,
                x=x,
                y=y,
                title=title,
                theme=theme,
                font_size=font_size,
                font_family=font_family,
                line_numbers=line_numbers,
                w=w,
                h=h,
                frame_id=frame_id,
            )

        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def list_fonts(
            category: FontCategory | None = None,
        ) -> FontListResult:
            """Discover and list available system fonts and semantic font categories."""
            return invoke(service.list_fonts, category=category)

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
        run_in_thread=False,
    )
    def draw_architecture(
        prompt: NonEmptyText,
        strokeColor: Color | None = None,
        backgroundColor: Color | None = None,
        fillStyle: FillStyle | None = None,
        strokeWidth: StrokeWidth | None = None,
        strokeStyle: StrokeStyle | None = None,
        opacity: Opacity | None = None,
        roughness: Roughness | None = None,
        font_family: FontFamily | None = None,
        font_size: FontSize | None = None,
    ) -> ArchitectureResult:
        """Replace the scene with a diagram from comma/newline-separated components.

        Supports ``"shape: label"`` syntax where shape can be
        ``rectangle``/``box``, ``circle``/``ellipse``, or ``diamond``.
        Components are arranged horizontally with automatic connectors.

        All style parameters are optional and apply globally to every element.
        """
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

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def draw_graph(
            nodes: list[GraphNode],
            edges: list[GraphEdge],
            clusters: list[GraphCluster] | None = None,
            layout: LayoutType = "layered",
            direction: Direction = "horizontal",
            elbowed: Boolean = False,
            roundness: Roundness | None = None,
            font_family: FontFamily | None = None,
            font_size: FontSize | None = None,
            cycle_fallback: Boolean = False,
        ) -> GraphResult:
            """Replace the scene with a structured graph and return stable ID mappings."""
            return invoke(
                service.draw_graph,
                [node.model_dump() for node in nodes],
                [edge.model_dump() for edge in edges],
                clusters=[cluster.model_dump() for cluster in clusters]
                if clusters
                else None,
                layout=layout,
                direction=direction,
                elbowed=elbowed,
                roundness=roundness,
                font_family=font_family,
                font_size=font_size,
                cycle_fallback=cycle_fallback,
            )

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def set_element_locked(
            element_ids: list[ElementId],
            locked: Boolean = True,
        ) -> LockResult | UnlockResult:
            """Lock or unlock elements and their bound labels to prevent or permit mutations."""
            return invoke(service.set_element_locked, element_ids, locked=locked)

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def lock_elements(element_ids: list[ElementId]) -> LockResult:
            """Lock elements and their bound labels to protect them from unintended mutations."""
            return invoke(service.set_element_locked, element_ids, locked=True)

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def unlock_elements(element_ids: list[ElementId]) -> UnlockResult:
            """Unlock previously locked elements and their bound labels."""
            return invoke(service.set_element_locked, element_ids, locked=False)

        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def manage_groups(
            element_ids: list[ElementId] | None = None,
            group_id: str | None = None,
            action: Literal["group", "ungroup"] = "group",
        ) -> GroupResult | UngroupResult:
            """Group or ungroup multiple elements together."""
            return invoke(service.manage_groups, element_ids=element_ids, group_id=group_id, action=action)

        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def group_elements(element_ids: list[ElementId]) -> GroupResult:
            """Group multiple elements together so they move and behave as a cohesive group."""
            return invoke(service.manage_groups, element_ids=element_ids, action="group")

        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def ungroup_elements(
            element_ids: list[ElementId] | None = None,
            group_id: str | None = None,
        ) -> UngroupResult:
            """Disband an element group by group_id or remove elements from their groups."""
            return invoke(service.manage_groups, element_ids=element_ids, group_id=group_id, action="ungroup")

    @mcp.tool(
        annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
        run_in_thread=False,
    )
    def draw_mermaid(
        mermaid_code: NonEmptyText,
        direction: Direction | None = None,
        layout: LayoutType = "layered",
        elbowed: Boolean = False,
        roundness: Roundness | None = None,
    ) -> GraphResult:
        """Parse Mermaid flowchart/graph code and render it directly to the Excalidraw scene."""
        return invoke(
            service.draw_mermaid,
            mermaid_code=mermaid_code,
            direction=direction,
            layout=layout,
            elbowed=elbowed,
            roundness=roundness,
        )

    if is_full:
        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def get_viewport() -> ViewportResult:
            """Get current canvas camera viewport settings (scroll coordinates, zoom level, background color)."""
            return invoke(service.get_viewport)

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def set_viewport(
            scroll_x: Coordinate | None = None,
            scroll_y: Coordinate | None = None,
            zoom: float | None = None,
            background_color: Color | None = None,
            focus_element_ids: list[ElementId] | None = None,
            padding: PreviewPadding = 50,
        ) -> ViewportResult | FocusResult:
            """Set canvas camera viewport scroll offsets, zoom level, background color, or focus on elements."""
            return invoke(
                service.set_viewport,
                scroll_x=scroll_x,
                scroll_y=scroll_y,
                zoom=zoom,
                background_color=background_color,
                focus_element_ids=focus_element_ids,
                padding=padding,
            )

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def focus_elements(
            element_ids: list[ElementId] | None = None,
            padding: PreviewPadding = 50,
        ) -> FocusResult:
            """Center and zoom the viewport camera to frame specified elements or the entire diagram."""
            return invoke(service.set_viewport, focus_element_ids=element_ids, padding=padding)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def get_scene_summary() -> SceneSummaryResult:
        """Return structured numerical metrics and topological metadata (counts, element dimensions, layers, code blocks, text contents) for layout planning."""
        return invoke(service.get_scene_summary)

    if is_full:
        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=False, openWorldHint=True),
            run_in_thread=False,
        )
        def export_to_excalidraw_url(name: SceneName | None = None) -> ShareUrlResult:
            """Publish the scene to excalidraw.com with client-side encryption and return a shareable URL."""
            return invoke(service.export_to_excalidraw_url, name=name)

    @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
    def describe_scene(detailed: Boolean = True) -> SceneDescriptionResult:
        """Generate a human/agent-readable natural language prose description of the diagram's spatial layout, clusters, and connectivity for cognitive verification."""
        return invoke(service.describe_scene, detailed=detailed)

    if is_full:
        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def get_canvas_screenshot(
            scale: PreviewScale = 1.0,
            padding: PreviewPadding = 40,
            background: Boolean = True,
        ) -> Image:
            """Alias for preview (DEPRECATED: Use preview instead). Render an inline PNG screenshot of the current canvas with embedded metadata."""
            import warnings

            warnings.warn(
                "get_canvas_screenshot is deprecated; use preview instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return preview(scale=scale, padding=padding, background=background)

        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def get_resource(
            uri: str | None = None,
            resource_type: str | None = None,
            identifier: str | None = None,
        ) -> ResourceResult:
            """Retrieve scene, library, theme, or element resources through a unified interface."""
            return invoke(
                service.get_resource,
                uri=uri,
                resource_type=resource_type,
                identifier=identifier,
            )

        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def read_diagram_guide(topic: str | None = None) -> DiagramGuideResult:
            """Read practical guidelines for layout, spacing, colors, typography, grouping, arrows, and readability."""
            return invoke(service.read_diagram_guide, topic=topic)

        @mcp.tool(annotations=MUTATING, run_in_thread=False)
        def duplicate_elements(
            element_ids: list[ElementId],
            offset_x: Coordinate = 20.0,
            offset_y: Coordinate = 20.0,
        ) -> DuplicateResult:
            """Duplicate multiple elements with spatial offsets, relationship remapping, and internal binding preservation."""
            return invoke(
                service.duplicate_elements,
                element_ids=element_ids,
                offset_x=offset_x,
                offset_y=offset_y,
            )

        @mcp.tool(
            annotations=ToolAnnotations(destructiveHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def import_scene(
            data: str,
            mode: Literal["replace", "merge"] = "replace",
            offset_x: Coordinate = 0.0,
            offset_y: Coordinate = 0.0,
        ) -> ImportResult:
            """Import scene from raw JSON, .excalidraw file, Obsidian .excalidraw.md, or embedded PNG with collision prevention."""
            return invoke(
                service.import_scene,
                data=data,
                mode=mode,
                offset_x=offset_x,
                offset_y=offset_y,
            )

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=True),
            run_in_thread=False,
        )
        def start_live_server(host: str = "127.0.0.1", port: int = 8080) -> LiveServerResult:
            """Start the background browser-connected Excalidraw live canvas server with real-time synchronization."""
            return invoke(service.start_live_server, host=host, port=port)

        @mcp.tool(
            annotations=ToolAnnotations(idempotentHint=True, openWorldHint=False),
            run_in_thread=False,
        )
        def stop_live_server() -> LiveServerResult:
            """Stop the background live canvas server."""
            return invoke(service.stop_live_server)

        @mcp.tool(annotations=READ_ONLY, run_in_thread=False)
        def get_live_server_status() -> LiveServerResult:
            """Check status of the browser-connected live canvas server."""
            return invoke(service.get_live_server_status)

    @mcp.resource("excalidraw://capabilities", mime_type="application/json")
    def capabilities_resource() -> str:
        """Read active server capabilities, toolset mode, and configuration metadata."""
        import json
        from .config import scene_directory, max_elements

        info = {
            "active_toolset": active_toolset,
            "available_toolsets": ["core", "full"],
            "server_version": "0.1.0",
            "tool_count": 46 if is_full else 25,
            "capabilities": {
                "generators": ["mermaid", "architecture_dsl"]
                + (["sugiyama_graph"] if is_full else []),
                "export": ["png", "excalidraw_json"],
                "repair": "5-phase topological auto_fix_layout with rollback",
                "full_only_features": [
                    "live_server",
                    "draw_graph",
                    "batch_mutate",
                    "add_code_block",
                    "get_viewport",
                    "set_viewport",
                    "focus_elements",
                    "lock_elements",
                    "unlock_elements",
                    "group_elements",
                    "ungroup_elements",
                    "find_elements",
                    "duplicate_elements",
                    "import_scene",
                    "export_to_excalidraw_url",
                    "list_saved_scenes",
                    "list_fonts",
                    "read_diagram_guide",
                    "get_resource",
                ],
            },
            "config": {
                "scene_dir": str(scene_directory()),
                "max_elements": max_elements(),
            },
            "upgrade_instructions": "To enable advanced tools, set environment variable EXCALIDRAW_TOOLSET=full.",
        }
        return json.dumps(info, indent=2)

    return mcp


mcp = create_server()


def main():
    """Run the installed stdio MCP server."""
    mcp.run()


def run():
    """Run the installed stdio MCP server."""
    mcp.run(show_banner=False)


if __name__ == "__main__":
    main()
