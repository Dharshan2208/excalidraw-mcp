"""Types shared by MCP schemas and structured graph operations."""

from typing import Annotated, Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from excalidraw_mcp.validation import COLOR_PATTERN

Coordinate = Annotated[float, Field(strict=True, ge=-100_000, le=100_000)]
Dimension = Annotated[float, Field(strict=True, gt=0, le=100_000)]
Label = Annotated[str, Field(strict=True, max_length=2_000)]
ElementId = Annotated[
    str, Field(strict=True, min_length=1, max_length=200, pattern=r".*\S.*")
]
Color = Annotated[str, Field(strict=True, pattern=f"^{COLOR_PATTERN}$")]
Boolean = Annotated[bool, Field(strict=True)]
SceneName = Annotated[
    str,
    Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$"),
]
Opacity = Annotated[int, Field(strict=True, ge=0, le=100)]
StrokeWidth = Annotated[int, Field(strict=True, ge=1, le=20)]
FontSize = Annotated[int, Field(strict=True, ge=8, le=200)]
Roughness = Annotated[int, Field(strict=True, ge=0, le=3)]
FillStyle = Literal["solid", "hachure", "cross-hatch", "zigzag"]
StrokeStyle = Literal["solid", "dashed", "dotted"]
ShapeType = Literal["rectangle", "ellipse", "diamond"]
ElementType = Literal["rectangle", "ellipse", "diamond", "arrow", "text", "frame"]
Roundness = Literal["adaptive", "round", "sharp"]
CodeTheme = Literal["dark", "monokai", "github-dark", "light", "solarized-dark"]
FontCategory = Literal["sans-serif", "monospace", "serif", "handwriting"]
FontFamily = (
    Literal["excalifont", "sans-serif", "monospace", "comic-shanns", "handwriting"]
    | str
    | int
)
LayoutType = Literal["layered", "horizontal", "vertical"]
Direction = Literal["horizontal", "vertical"]
Offset = Annotated[int, Field(strict=True, ge=0)]
PageLimit = Annotated[int, Field(strict=True, ge=1, le=200)]
PreviewScale = Annotated[float, Field(strict=True, ge=0.25, le=4.0)]
PreviewPadding = Annotated[int, Field(strict=True, ge=0, le=200)]
NonEmptyText = Annotated[
    str, Field(strict=True, min_length=1, max_length=2_000, pattern=r".*\S.*")
]
RepairScope = Literal["all", "overlaps", "connectors", "containment", "text", "spacing"]
Aggressiveness = Literal["gentle", "balanced", "aggressive"]


class GraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: ElementId
    label: Annotated[
        str, Field(strict=True, min_length=1, max_length=2_000, pattern=r".*\S.*")
    ]
    shape: ShapeType = "rectangle"
    cluster: ElementId | None = None
    strokeColor: Color | None = None
    backgroundColor: Color | None = None
    fillStyle: FillStyle | None = None
    strokeWidth: StrokeWidth | None = None
    strokeStyle: StrokeStyle | None = None
    opacity: Opacity | None = None
    roundness: Roundness | None = None
    font_family: FontFamily | None = None
    font_size: FontSize | None = None


class GraphCluster(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: ElementId
    label: Annotated[
        str, Field(strict=True, min_length=1, max_length=2_000, pattern=r".*\S.*")
    ]


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: ElementId | None = None
    source: ElementId
    target: ElementId
    label: Label = ""
    elbowed: Boolean = False
    strokeColor: Color | None = None
    strokeWidth: StrokeWidth | None = None
    strokeStyle: StrokeStyle | None = None
    opacity: Opacity | None = None
    font_family: FontFamily | None = None
    font_size: FontSize | None = None

    @model_validator(mode="after")
    def distinct_ends(self):
        if self.source == self.target:
            raise ValueError("source and target must differ")
        return self


class CreateResult(TypedDict):
    rectangle_id: NotRequired[str]
    circle_id: NotRequired[str]
    diamond_id: NotRequired[str]
    arrow_id: NotRequired[str]
    text_id: NotRequired[str]
    frame_id: NotRequired[str]
    label_id: NotRequired[str | None]


class StatusResult(TypedDict):
    status: str


class ElementResult(TypedDict):
    element: dict[str, Any]
    revision: int


class ScenePage(TypedDict):
    revision: int
    total: int
    offset: int
    limit: int
    elements: list[dict[str, Any]]
    has_more: bool


class GraphResult(TypedDict):
    status: str
    nodes: int
    edges: int
    node_map: dict[str, dict[str, str | None]]
    edge_map: dict[str, dict[str, str | None]]
    cluster_map: NotRequired[dict[str, str]]
    revision: int


class BatchOperation(BaseModel):
    model_config = ConfigDict(extra="allow")
    action: Literal[
        "add_rectangle",
        "add_circle",
        "add_diamond",
        "add_arrow",
        "add_text",
        "add_frame",
        "add_code_block",
        "connect",
        "move",
        "resize",
        "update_element",
        "delete",
        "lock",
        "unlock",
        "group",
        "ungroup",
        "duplicate",
        "duplicate_elements",
        "resolve_layout",
        "auto_fix_layout",
    ]
    client_id: str | None = None
    x: float | None = None
    y: float | None = None
    x2: float | None = None
    y2: float | None = None
    w: float | None = None
    h: float | None = None
    width: float | None = None
    height: float | None = None
    size: float | None = None
    label: str | None = None
    content: str | None = None
    name: str | None = None
    font_size: int | None = None
    element_id: str | None = None
    source_id: str | None = None
    target_id: str | None = None
    element_ids: list[str] | None = None
    offset_x: float | None = None
    offset_y: float | None = None
    group_id: str | None = None
    frame_id: str | None = None
    code: str | None = None
    language: str | None = None
    title: str | None = None
    theme: CodeTheme | None = None
    font_family: FontFamily | None = None
    line_numbers: bool | None = None
    elbowed: bool | None = None
    roundness: Roundness | None = None
    strokeColor: str | None = None
    backgroundColor: str | None = None
    fillStyle: FillStyle | None = None
    strokeWidth: int | None = None
    strokeStyle: StrokeStyle | None = None
    opacity: int | None = None
    roughness: int | None = None
    min_gap_x: float | None = None
    min_gap_y: float | None = None
    min_gap: float | None = None
    repair_scope: str | None = None
    aggressiveness: str | None = None
    dry_run: bool | None = None
    layer_gap: float | None = None
    frame_padding: float | None = None


class BatchResult(TypedDict):
    status: str
    operations_executed: int
    results: list[dict[str, Any]]
    ref_map: dict[str, str]
    revision: int


class ElementSummary(TypedDict):
    id: str
    type: str
    label: NotRequired[str | None]
    name: NotRequired[str | None]
    x: float
    y: float
    width: float
    height: float
    frame_id: NotRequired[str | None]
    container_id: NotRequired[str | None]
    bound_element_ids: list[str]
    stroke_color: NotRequired[str | None]
    background_color: NotRequired[str | None]


class FindResult(TypedDict):
    total: int
    matches: list[ElementSummary]
    revision: int


class DeleteResult(TypedDict):
    status: str
    element_id: str
    deleted_ids: list[str]


class MoveResult(TypedDict):
    status: str
    element_id: str
    x: float
    y: float


class ResizeResult(TypedDict):
    status: str
    element_id: str
    width: float
    height: float


class UpdateResult(TypedDict):
    status: str
    element_id: str
    label_id: str | None


class ConnectResult(TypedDict):
    arrow_id: str
    label_id: str | None
    source_id: str
    target_id: str


class SaveResult(TypedDict):
    path: str
    elements: int
    status: str


class LoadResult(TypedDict):
    loaded: int
    name: str
    status: str


class UndoResult(TypedDict):
    status: str
    revision: int
    history_depth: int


class SavedScenesResult(TypedDict):
    scenes: list[str]
    count: int


class ArchitectureResult(TypedDict):
    status: str
    nodes: int
    edges: int
    node_map: dict[str, dict[str, str | None]]
    edge_map: dict[str, dict[str, str | None]]
    revision: int
    url: str | None
    next_step: str


class PngExportResult(TypedDict):
    status: str
    name: str
    path: str
    bytes: int
    width: int
    height: int
    scale: float
    revision: int


class CodeBlockResult(TypedDict):
    status: str
    container_id: str
    text_id: str
    width: float
    height: float
    revision: int


class FontInfo(TypedDict):
    family: str
    style: str
    category: str
    path: str


class FontListResult(TypedDict):
    fonts: list[FontInfo]
    total: int
    defaults: dict[str, str]


class LockResult(TypedDict):
    status: str
    element_ids: list[str]
    revision: int


class UnlockResult(TypedDict):
    status: str
    element_ids: list[str]
    revision: int


class GroupResult(TypedDict):
    status: str
    group_id: str
    element_ids: list[str]
    revision: int


class UngroupResult(TypedDict):
    status: str
    affected_elements: list[str]
    removed_group_ids: list[str]
    revision: int


class ViewportResult(TypedDict):
    scroll_x: float
    scroll_y: float
    zoom: float
    view_background_color: str
    revision: int


class FocusResult(TypedDict):
    status: str
    scroll_x: float
    scroll_y: float
    zoom: float
    bounding_box: dict[str, float]
    focused_element_ids: list[str]
    revision: int


class SceneSummaryResult(TypedDict):
    element_count: int
    type_counts: dict[str, int]
    frames: list[dict[str, Any]]
    groups: list[dict[str, Any]]
    connectors: list[dict[str, Any]]
    code_blocks: list[dict[str, Any]]
    standalone_elements: list[str]
    bounds: dict[str, float] | None
    description: str
    revision: int


class ShareUrlResult(TypedDict):
    status: str
    url: str
    id: str
    revision: int
    backup_path: NotRequired[str | None]


class SceneDescriptionResult(TypedDict):
    summary: str
    element_count: int
    layout_type: str
    elements: list[dict[str, Any]]
    connections: list[dict[str, Any]]
    bounds: dict[str, float] | None
    revision: int


class DiagramGuideResult(TypedDict):
    topic: str
    guide: Any
    available_topics: list[str]


class DuplicateResult(TypedDict):
    status: str
    original_ids: list[str]
    duplicated_ids: list[str]
    id_mapping: dict[str, str]
    revision: int


class ImportResult(TypedDict):
    status: str
    mode: str
    elements_imported: int
    total_elements: NotRequired[int]
    id_mapping: NotRequired[dict[str, str]]
    revision: int


class ResourceResult(TypedDict):
    resource_type: str
    identifier: str
    name: NotRequired[str]
    element_count: NotRequired[int]
    document: NotRequired[dict[str, Any]]
    theme: NotRequired[dict[str, Any]]
    library: NotRequired[dict[str, Any]]
    element: NotRequired[dict[str, Any]]
    label: NotRequired[dict[str, Any] | None]
    frame: NotRequired[dict[str, Any] | None]
    connected_arrows: NotRequired[list[dict[str, Any]]]
    group_peers: NotRequired[list[str]]
    available_themes: NotRequired[list[str]]
    available_libraries: NotRequired[list[str]]
    source: NotRequired[str]
    revision: NotRequired[int]


class LiveServerResult(TypedDict):
    status: str
    url: NotRequired[str | None]
    host: NotRequired[str]
    port: NotRequired[int]
    is_running: NotRequired[bool]
    active_clients: NotRequired[int]


class LayoutIssue(TypedDict):
    id: str
    type: str
    severity: str
    element_ids: list[str]
    description: str
    details: NotRequired[dict[str, Any]]


class LayoutChange(TypedDict):
    element_id: str
    change_type: str
    description: str
    before: NotRequired[dict[str, Any]]
    after: NotRequired[dict[str, Any]]


class AutoFixLayoutResult(TypedDict):
    status: str
    dry_run: bool
    initial_issues: list[LayoutIssue]
    final_issues: list[LayoutIssue]
    fixed_issues_count: int
    unresolved_issues: list[LayoutIssue]
    planned_changes: list[dict[str, Any]]
    applied_changes: list[LayoutChange]
    changed_element_ids: list[str]
    skipped_repairs: list[dict[str, Any]]
    warnings: list[str]
    rolled_back: bool
    revision: int


