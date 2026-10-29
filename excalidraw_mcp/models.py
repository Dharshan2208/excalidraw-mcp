"""Document boundary for the supported editable subset; unknown fields survive."""

import json
import math
from copy import deepcopy
from typing import Any, NotRequired, TypedDict, cast

from excalidraw_mcp.config import max_elements
from excalidraw_mcp.errors import SceneError


class Element(TypedDict):
    id: str
    type: str
    x: float
    y: float
    width: NotRequired[float]
    height: NotRequired[float]
    version: NotRequired[int]
    versionNonce: NotRequired[int]
    updated: NotRequired[int]
    isDeleted: NotRequired[bool]
    angle: NotRequired[float]
    elbowed: NotRequired[bool]
    containerId: NotRequired[str | None]
    boundElements: NotRequired[list[dict[str, str]] | None]
    points: NotRequired[list[list[float]]]
    startBinding: NotRequired[dict[str, Any] | None]
    endBinding: NotRequired[dict[str, Any] | None]


class SceneDocument(TypedDict):
    type: str
    version: int
    source: NotRequired[str]
    elements: list[Element]
    appState: dict[str, Any]
    files: dict[str, Any]


def new_document(elements: list[Element] | None = None) -> SceneDocument:
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "https://excalidraw.com",
        "elements": [] if elements is None else elements,
        "appState": {},
        "files": {},
    }


def _finite_number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_document(document: dict[str, Any]) -> SceneDocument:
    """Validate structural invariants while retaining unfamiliar imported fields."""
    if not isinstance(document, dict) or document.get("type") != "excalidraw":
        raise SceneError("Expected an Excalidraw document")
    if type(document.get("version")) is not int or document["version"] != 2:
        raise SceneError("Only Excalidraw document version 2 is supported")
    if not isinstance(document.get("elements"), list):
        raise SceneError("Document elements must be a list")
    element_limit = max_elements()
    if len(document["elements"]) > element_limit:
        raise SceneError(
            f"Document exceeds the configured limit of {element_limit} elements"
        )
    for field in ("appState", "files"):
        if not isinstance(document.get(field, {}), dict):
            raise SceneError(f"Document {field} must be an object")
    ids = set()
    for element in document["elements"]:
        if not isinstance(element, dict):
            raise SceneError("Each element must be an object")
        element_id = element.get("id")
        if (
            not isinstance(element_id, str)
            or not element_id.strip()
            or element_id in ids
        ):
            raise SceneError("Element IDs must be nonempty, unique strings")
        ids.add(element_id)
        if "isDeleted" in element and type(element["isDeleted"]) is not bool:
            raise SceneError(f"Element {element_id} has invalid isDeleted flag")
        if not isinstance(element.get("type"), str) or not element["type"].strip():
            raise SceneError(f"Element {element_id} needs a type")
        for field in ("x", "y", "width", "height"):
            if field in ("width", "height") and field not in element:
                continue
            value = element.get(field)
            if not _finite_number(value):
                raise SceneError(f"Element {element_id} needs a finite {field}")
            if field in ("width", "height") and (value is None or value < 0):
                raise SceneError(f"Element {element_id} has negative {field}")
    try:
        json.dumps(document, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise SceneError("Document must contain finite JSON data") from exc
    result = deepcopy(document)
    result.setdefault("appState", {})
    result.setdefault("files", {})
    return cast(SceneDocument, result)


def normalize_relationships(document: SceneDocument) -> None:
    """Rebuild reverse bindings from canonical references; reject dangling ones.

    Tombstones are preserved but do not participate in active relationships.
    """
    active = {el["id"]: el for el in document["elements"] if not el.get("isDeleted")}
    known_containers = {"rectangle", "ellipse", "diamond", "arrow"}
    reverse: dict[str, list[dict[str, str]]] = {element_id: [] for element_id in active}
    labels = set()
    for el in active.values():
        frame_id = el.get("frameId")
        if frame_id is not None:
            if (
                not isinstance(frame_id, str)
                or frame_id not in active
                or frame_id == el["id"]
                or active[frame_id]["type"] != "frame"
            ):
                raise SceneError(f"Invalid frameId for {el['id']}")
        container_id = el.get("containerId")
        if el["type"] == "text" and container_id is not None:
            if (
                not isinstance(container_id, str)
                or container_id not in active
                or container_id == el["id"]
                or active[container_id]["type"] not in known_containers
            ):
                raise SceneError(f"Invalid text container for {el['id']}")
            if container_id in labels:
                raise SceneError("A container can own only one text label")
            labels.add(container_id)
            reverse[container_id].append({"id": el["id"], "type": "text"})
        elif el["type"] in known_containers and container_id is not None:
            raise SceneError(f"Invalid text container for {el['id']}")
        if el["type"] == "arrow":
            points = el.get("points")
            if (
                not isinstance(points, list)
                or len(points) < 2
                or any(
                    not isinstance(p, list)
                    or len(p) != 2
                    or not all(_finite_number(v) for v in p)
                    for p in points
                )
            ):
                raise SceneError(f"Arrow {el['id']} needs at least two finite points")
            for end in ("startBinding", "endBinding"):
                binding = el.get(end)
                if binding is None:
                    continue
                target = binding.get("elementId") if isinstance(binding, dict) else None
                if (
                    not isinstance(target, str)
                    or target not in active
                    or target == el["id"]
                    or active[target]["type"] == "arrow"
                    or active[target].get("containerId")
                ):
                    raise SceneError(f"Invalid {end} for {el['id']}")
                ref = {"id": el["id"], "type": "arrow"}
                if ref not in reverse[target]:
                    reverse[target].append(ref)
    for element_id, refs in reverse.items():
        el = active[element_id]
        # Unknown elements may use relationships introduced by newer Excalidraw
        # versions. Never interpret or rewrite those fields.
        if el["type"] not in known_containers:
            continue
        existing = el.get("boundElements")
        preserved = []
        if isinstance(existing, list):
            for ref in existing:
                if not isinstance(ref, dict):
                    preserved.append(ref)
                    continue
                ref_id = ref.get("id")
                referenced = active.get(ref_id) if isinstance(ref_id, str) else None
                known_ref = ref.get("type") in ("text", "arrow") and (
                    referenced is None
                    or referenced.get("type") in ("text", "arrow")
                )
                if not known_ref:
                    preserved.append(ref)
        if refs or preserved or "boundElements" in el:
            el["boundElements"] = preserved + refs
