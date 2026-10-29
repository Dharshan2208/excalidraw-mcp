"""Scene operations independent of MCP transport and server globals."""

import math
import os
import re
import uuid
from pathlib import Path
from typing import Any

from excalidraw_mcp.config import max_export_bytes
from excalidraw_mcp.elements import (
    arrow,
    bind_text,
    diamond,
    ellipse,
    frame,
    normalize_font_family,
    rect,
    text,
)
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.document import serialize_document
from excalidraw_mcp.models import _finite_number, new_document
from excalidraw_mcp.scene import list_scenes, load_scene, save_scene
from excalidraw_mcp.state import SceneState
from excalidraw_mcp.text_padding import required_container_size
from excalidraw_mcp.layout import boundary_point, clustered_layout, layered_layout, linear_layout, wrap_label
from excalidraw_mcp.parser import parse_architecture

SHAPES = {"rectangle": rect, "ellipse": ellipse, "diamond": diamond}


def _serialize_for_export(document):
    payload = serialize_document(document)
    size_limit = max_export_bytes()
    if len(payload.encode("utf-8")) > size_limit:
        raise SceneError(f"Export exceeds the configured limit of {size_limit} bytes")
    return payload


def _shape_elements(shape, x, y, w, h, label, style, frame_id=None):
    if label:
        font_size = style.get("font_size", style.get("fontSize", 20))
        font_family = style.get("font_family", style.get("fontFamily"))
        from .layout import wrap_text_to_shape
        from .fonts import measure_text_dimensions

        # Wrap text to target container width
        wrapped_label = wrap_text_to_shape(
            label, shape=shape, target_w=w, font_size=font_size, font_family=font_family
        )
        text_w, text_h, _ = measure_text_dimensions(
            wrapped_label, font_family=font_family, font_size=font_size
        )

        # Calculate minimum required shape dimensions for internal padding containment
        min_w, min_h = required_container_size(shape, text_w, text_h)

        # Auto-expand container if requested size is too small for text
        if min_w > w or min_h > h:
            w = max(w, min_w)
            h = max(h, min_h)

        shape_el = SHAPES[shape](x, y, w, h, **style)
        if frame_id:
            shape_el["frameId"] = frame_id
        label_style = {
            k: v
            for k, v in style.items()
            if k in (
                "strokeColor",
                "opacity",
                "fontFamily",
                "font_family",
                "fontSize",
                "font_size",
            )
        }
        label_el = text(x, y, wrapped_label, **label_style)
        if frame_id:
            label_el["frameId"] = frame_id
        bind_text(label_el, shape_el)
        _center_label(label_el, shape_el)
        return [shape_el, label_el]
    else:
        shape_el = SHAPES[shape](x, y, w, h, **style)
        if frame_id:
            shape_el["frameId"] = frame_id
        return [shape_el]


def _active(document):
    return {el["id"]: el for el in document["elements"] if not el.get("isDeleted")}


def _require(index, element_id):
    if element_id not in index:
        raise SceneError(f"Element '{element_id}' not found")
    return index[element_id]


def _translate(el, dx, dy):
    el["x"] += dx
    el["y"] += dy


def _label_for(index, container_id):
    return next(
        (el for el in index.values() if el.get("containerId") == container_id), None
    )


def _center_label(label, container):
    if (container.get("customData") or {}).get("type") in ("code_block", "code-block"):
        return
    if container["type"] == "arrow" and container.get("points"):
        pts = container["points"]
        if len(pts) > 2:
            from .routing import position_connector_label
            ax, ay = container.get("x", 0.0), container.get("y", 0.0)
            world_pts = [(ax + float(p[0]), ay + float(p[1])) for p in pts]
            lw = float(label.get("width", 80.0))
            lh = float(label.get("height", 25.0))
            lx, ly = position_connector_label(world_pts, lw, lh)
            label["x"] = lx
            label["y"] = ly
            return
        first, last = pts[0], pts[-1]
        cx = container["x"] + (first[0] + last[0]) / 2
        cy = container["y"] + (first[1] + last[1]) / 2
    else:
        cx = container["x"] + container.get("width", 0) / 2
        cy = container["y"] + container.get("height", 0) / 2
    label["x"], label["y"] = cx - label["width"] / 2, cy - label["height"] / 2


def _element_bounds(el):
    """Accurately compute the bounding box of any element, accounting for arrow/line points."""
    x, y = float(el.get("x", 0)), float(el.get("y", 0))
    w, h = float(el.get("width", 0)), float(el.get("height", 0))
    if el.get("type") in ("arrow", "line", "freedraw") and el.get("points"):
        pts_x = [x + float(p[0]) for p in el["points"]]
        pts_y = [y + float(p[1]) for p in el["points"]]
        return min(pts_x), min(pts_y), max(pts_x), max(pts_y)
    return x, y, x + w, y + h


def _as_layout_node(el):
    return {
        "id": el["id"],
        "shape": el["type"],
        "x": el["x"],
        "y": el["y"],
        "w": el["width"],
        "h": el["height"],
        "angle": el.get("angle", 0),
    }


def _reroute_connector(index, connector):
    if connector.get("elbowed") or connector.get("angle", 0):
        raise SceneError(
            "Resizing shapes attached to elbowed or rotated arrows is not supported yet"
        )
    start_id = (connector.get("startBinding") or {}).get("elementId")
    end_id = (connector.get("endBinding") or {}).get("elementId")
    if not start_id or not end_id or start_id not in index or end_id not in index:
        return
    source, target = index[start_id], index[end_id]
    start = boundary_point(_as_layout_node(source), _as_layout_node(target), 1)
    end = boundary_point(_as_layout_node(target), _as_layout_node(source), -1)
    connector["x"], connector["y"] = start
    connector["points"] = [[0, 0], [end[0] - start[0], end[1] - start[1]]]
    connector["width"], connector["height"] = (
        abs(end[0] - start[0]),
        abs(end[1] - start[1]),
    )
    label = _label_for(index, connector["id"])
    if label:
        _center_label(label, connector)


def _move_arrow_endpoints(el, dx, dy, start, end):
    if (not (start and end)) and (el.get("elbowed") or el.get("angle", 0)):
        raise SceneError(
            "Moving shapes attached to elbowed or rotated arrows is not supported yet"
        )
    world = [[el["x"] + p[0], el["y"] + p[1]] for p in el["points"]]
    if start and end:
        world = [[x + dx, y + dy] for x, y in world]
    else:
        if start:
            world[0][0] += dx
            world[0][1] += dy
        if end:
            world[-1][0] += dx
            world[-1][1] += dy
    el["x"], el["y"] = world[0]
    el["points"] = [[x - el["x"], y - el["y"]] for x, y in world]
    el["width"] = max(p[0] for p in world) - min(p[0] for p in world)
    el["height"] = max(p[1] for p in world) - min(p[1] for p in world)


class SceneService:
    def __init__(self, state: SceneState | None = None):
        self.state = state if state is not None else SceneState()
        self._live_server = None

    def add_shape(self, shape, x, y, w, h, label="", frame_id=None, **style):
        if shape not in SHAPES:
            raise SceneError("Shape must be rectangle, ellipse or diamond")
        elements = _shape_elements(shape, x, y, w, h, label, style, frame_id=frame_id)
        ids = self.state.add_many(elements)
        key = {
            "rectangle": "rectangle_id",
            "ellipse": "circle_id",
            "diamond": "diamond_id",
        }[shape]
        return {key: ids[0], "label_id": ids[1] if len(ids) > 1 else None}

    def add_arrow(self, x, y, x2, y2, label="", elbowed=False, **style):
        arrow_el = arrow(x, y, x2, y2, elbowed=elbowed, **style)
        elements = [arrow_el]
        if label:
            label_el = text(x, y, label, fontSize=14, **style)
            bind_text(label_el, arrow_el)
            _center_label(label_el, arrow_el)
            elements.append(label_el)
        ids = self.state.add_many(elements)
        return {"arrow_id": ids[0], "label_id": ids[1] if len(ids) > 1 else None}

    def add_text(
        self,
        x,
        y,
        content,
        font_size=20,
        font_family=None,
        frame_id=None,
        **style,
    ):
        if not isinstance(content, str) or not content.strip():
            raise SceneError("Text content cannot be empty")
        if frame_id:
            style["frameId"] = frame_id
        element = text(
            x,
            y,
            content,
            fontSize=font_size,
            fontFamily=font_family or 2,
            **style,
        )
        return {"text_id": self.state.add(element)}

    def get_element(self, element_id):
        element, revision = self.state.get_with_revision(element_id)
        if element is None or element.get("isDeleted"):
            raise SceneError(f"Element '{element_id}' not found")
        return {"element": element, "revision": revision}

    def get_scene(self, offset=0, limit=50):
        if (
            type(offset) is not int
            or type(limit) is not int
            or offset < 0
            or not 1 <= limit <= 200
        ):
            raise SceneError(
                "offset must be nonnegative and limit must be between 1 and 200"
            )
        document, revision = self.state.snapshot()
        elements = [el for el in document["elements"] if not el.get("isDeleted")]
        return {
            "revision": revision,
            "total": len(elements),
            "offset": offset,
            "limit": limit,
            "elements": elements[offset : offset + limit],
            "has_more": offset + limit < len(elements),
        }

    def list_saved_scenes(self):
        scenes = list_scenes()
        return {"scenes": scenes, "count": len(scenes)}

    def clear(self):
        self.state.clear()
        return {"status": "scene cleared"}

    def undo(self):
        return self.state.undo()

    def delete(self, element_id):
        def remove(document):
            index = _active(document)
            el = _require(index, element_id)
            if el.get("locked"):
                raise SceneError(f"Cannot delete locked element '{element_id}'")
            removed = {element_id}
            removed.update(
                el["id"] for el in index.values() if el.get("containerId") == element_id
            )
            document["elements"] = [
                el for el in document["elements"] if el["id"] not in removed
            ]
            for el in document["elements"]:
                if el.get("frameId") in removed:
                    el["frameId"] = None
                if el["type"] == "arrow" and not el.get("isDeleted"):
                    for end in ("startBinding", "endBinding"):
                        if (el.get(end) or {}).get("elementId") in removed:
                            el[end] = None
            return {
                "status": "deleted",
                "element_id": element_id,
                "deleted_ids": [key for key in index if key in removed],
            }

        return self.state.apply(remove)

    def move(self, element_id, x, y):
        if not _finite_number(x) or not _finite_number(y):
            raise SceneError("Move coordinates must be finite numbers")

        def move_elements(document):
            index = _active(document)
            el = _require(index, element_id)
            if el.get("locked"):
                raise SceneError(f"Cannot move locked element '{element_id}'")
            if el.get("containerId"):
                raise SceneError(
                    "Move the label's container instead of moving bound text independently"
                )
            dx, dy = x - el["x"], y - el["y"]
            if not dx and not dy:
                return {"status": "moved", "element_id": element_id, "x": x, "y": y}
            if el["type"] == "arrow" and el.get("elbowed"):
                raise SceneError("Moving elbowed arrows is not supported yet")

            grouped_members = []
            if el.get("groupIds"):
                target_groups = set(el["groupIds"])
                for other in index.values():
                    if other["id"] != element_id and any(
                        g in target_groups for g in other.get("groupIds", [])
                    ):
                        if other.get("locked"):
                            raise SceneError(
                                f"Cannot move locked element '{other['id']}' in group"
                            )
                        grouped_members.append(other)

            if el["type"] == "frame":
                for child in index.values():
                    if child.get("frameId") == element_id:
                        if child.get("locked"):
                            raise SceneError(
                                f"Cannot move locked element '{child['id']}' in frame"
                            )

            _translate(el, dx, dy)
            moved_targets = {element_id}
            owned_labels = {
                label["containerId"]: label
                for label in index.values()
                if label.get("containerId")
            }
            for member in grouped_members:
                _translate(member, dx, dy)
                moved_targets.add(member["id"])
            if el["type"] == "frame":
                for child in index.values():
                    if child.get("frameId") == element_id:
                        _translate(child, dx, dy)
                        moved_targets.add(child["id"])
            for label in index.values():
                if label.get("containerId") in moved_targets:
                    _translate(label, dx, dy)
                    moved_targets.add(label["id"])
            if el["type"] == "arrow":
                # A coordinate move intentionally detaches the arrow from shapes.
                el["startBinding"] = None
                el["endBinding"] = None
            for connector in index.values():
                if connector["type"] != "arrow" or connector["id"] in moved_targets:
                    continue
                start = (connector.get("startBinding") or {}).get(
                    "elementId"
                ) in moved_targets
                end = (connector.get("endBinding") or {}).get(
                    "elementId"
                ) in moved_targets
                if start or end:
                    _move_arrow_endpoints(connector, dx, dy, start, end)
                    # Preserve the label's offset from the endpoint midpoint.
                    label = owned_labels.get(connector["id"])
                    if label:
                        _translate(
                            label,
                            dx * (int(start) + int(end)) / 2,
                            dy * (int(start) + int(end)) / 2,
                        )
            return {"status": "moved", "element_id": element_id, "x": x, "y": y}

        return self.state.apply(move_elements)

    def resize(self, element_id, width, height):
        if (
            not _finite_number(width)
            or not _finite_number(height)
            or width <= 0
            or height <= 0
        ):
            raise SceneError("width and height must be positive finite numbers")

        def resize_element(document):
            index = _active(document)
            el = _require(index, element_id)
            if el.get("locked"):
                raise SceneError(f"Cannot resize locked element '{element_id}'")
            if el["type"] not in (*SHAPES, "frame"):
                raise SceneError(
                    "Only rectangle, ellipse, diamond and frame elements can be resized"
                )
            el["width"], el["height"] = width, height
            label = _label_for(index, element_id)
            if label:
                _center_label(label, el)
            for connector in index.values():
                if connector["type"] == "arrow" and any(
                    (connector.get(end) or {}).get("elementId") == element_id
                    for end in ("startBinding", "endBinding")
                ):
                    _reroute_connector(index, connector)
            return {
                "status": "resized",
                "element_id": element_id,
                "width": width,
                "height": height,
            }

        return self.state.apply(resize_element)

    def update_element(
        self,
        element_id,
        label=None,
        stroke_color=None,
        background_color=None,
        fill_style=None,
        stroke_width=None,
        stroke_style=None,
        opacity=None,
        roughness=None,
        roundness=None,
        frame_id=None,
        elbowed=None,
        font_family=None,
        font_size=None,
    ):
        updates = {
            "strokeColor": stroke_color,
            "backgroundColor": background_color,
            "fillStyle": fill_style,
            "strokeWidth": stroke_width,
            "strokeStyle": stroke_style,
            "opacity": opacity,
            "roughness": roughness,
        }
        updates = {key: value for key, value in updates.items() if value is not None}
        if roundness is not None:
            if roundness == "adaptive":
                updates["roundness"] = {"type": 3}
            elif roundness == "round":
                updates["roundness"] = {"type": 2}
            elif roundness == "sharp":
                updates["roundness"] = None
            elif isinstance(roundness, dict):
                updates["roundness"] = roundness
        if elbowed is not None:
            updates["elbowed"] = bool(elbowed)
        if (
            label is None
            and frame_id is None
            and not updates
            and font_family is None
            and font_size is None
        ):
            raise SceneError("Provide a label or at least one style or font update")

        def update(document):
            index = _active(document)
            el = _require(index, element_id)
            if el.get("locked"):
                raise SceneError(f"Cannot update locked element '{element_id}'")

            if frame_id is not None:
                if frame_id == "":
                    el["frameId"] = None
                    lbl = _label_for(index, element_id)
                    if lbl:
                        lbl["frameId"] = None
                else:
                    _require(index, frame_id)
                    if index[frame_id]["type"] != "frame":
                        raise SceneError(f"Element '{frame_id}' is not a frame")
                    el["frameId"] = frame_id
                    lbl = _label_for(index, element_id)
                    if lbl:
                        lbl["frameId"] = frame_id

            if el["type"] == "frame" and label is not None:
                el["name"] = label
                el.update(updates)
                return {
                    "status": "updated",
                    "element_id": element_id,
                    "label_id": None,
                }
            elif el["type"] == "text":
                container_id = el.get("containerId")
                container = index.get(container_id) if container_id else None
                label_id = el["id"]
                if font_family is not None:
                    el["fontFamily"] = normalize_font_family(font_family)
                    if isinstance(font_family, str) and font_family.strip().lower() not in (
                        "1",
                        "2",
                        "3",
                        "4",
                        "excalifont",
                        "virgil",
                        "sans-serif",
                        "sans",
                        "helvetica",
                        "normal",
                        "monospace",
                        "mono",
                        "code",
                        "cascadia",
                        "comic-shanns",
                        "comic",
                        "comic shanns",
                        "handwriting",
                        "hand-drawn",
                        "hand",
                    ):
                        el.setdefault("customData", {})["fontFamily"] = font_family.strip()
                    elif "customData" in el and "fontFamily" in el["customData"]:
                        el["customData"]["fontFamily"] = str(font_family)
                if font_size is not None:
                    el["fontSize"] = font_size

                if label is not None:
                    if not label:
                        if container is None:
                            raise SceneError(
                                "Standalone text cannot be empty; use delete instead"
                            )
                        document["elements"] = [
                            item
                            for item in document["elements"]
                            if item["id"] != el["id"]
                        ]
                        index.pop(el["id"], None)
                        return {
                            "status": "updated",
                            "element_id": element_id,
                            "label_id": None,
                        }
                    else:
                        active_label = label
                else:
                    active_label = el.get("text", "")

                from .fonts import measure_text_dimensions
                from .layout import wrap_text_to_shape

                if container and container.get("type") in ("rectangle", "ellipse", "diamond"):
                    c_type = container["type"]
                    c_w = float(container.get("width", 100.0))
                    c_h = float(container.get("height", 100.0))
                    wrapped = wrap_text_to_shape(
                        active_label,
                        shape=c_type,
                        target_w=c_w,
                        font_size=el.get("fontSize", 20),
                        font_family=el.get("fontFamily"),
                    )
                    el["text"] = el["originalText"] = wrapped
                    tw, th, _ = measure_text_dimensions(
                        wrapped, font_family=el.get("fontFamily"), font_size=el.get("fontSize", 20)
                    )
                    el["width"] = tw
                    el["height"] = th

                    min_w, min_h = required_container_size(c_type, tw, th)

                    if min_w > c_w or min_h > c_h:
                        new_w = max(c_w, min_w)
                        new_h = max(c_h, min_h)
                        container["x"] = (container["x"] + c_w / 2.0) - new_w / 2.0
                        container["y"] = (container["y"] + c_h / 2.0) - new_h / 2.0
                        container["width"] = new_w
                        container["height"] = new_h

                    _center_label(el, container)
                else:
                    if label is not None:
                        el["text"] = el["originalText"] = label
                    tw, th, _ = measure_text_dimensions(
                        el["text"], font_family=el.get("fontFamily"), font_size=el.get("fontSize", 20)
                    )
                    el["width"] = tw
                    el["height"] = th
                    if container:
                        _center_label(el, container)

                el.update(updates)
                return {
                    "status": "updated",
                    "element_id": element_id,
                    "label_id": label_id,
                }
            else:
                target = _label_for(index, element_id)
                label_id = target.get("id") if target else None
                from .fonts import measure_text_dimensions
                from .layout import wrap_text_to_shape

                if label is not None:
                    if target is None:
                        if label:
                            label_style = {
                                "strokeColor": updates.get(
                                    "strokeColor", el.get("strokeColor", "#1e1e1e")
                                ),
                                "opacity": updates.get("opacity", el.get("opacity", 100)),
                            }
                            f_size = font_size if font_size is not None else (14 if el["type"] == "arrow" else 20)
                            f_fam = font_family or 2
                            c_type = el["type"]
                            c_w = float(el.get("width", 100.0))
                            c_h = float(el.get("height", 100.0))

                            if c_type in ("rectangle", "ellipse", "diamond"):
                                wrapped = wrap_text_to_shape(
                                    label, shape=c_type, target_w=c_w, font_size=f_size, font_family=f_fam
                                )
                                tw, th, _ = measure_text_dimensions(
                                    wrapped, font_family=f_fam, font_size=f_size
                                )
                                min_w, min_h = required_container_size(c_type, tw, th)

                                if min_w > c_w or min_h > c_h:
                                    new_w = max(c_w, min_w)
                                    new_h = max(c_h, min_h)
                                    el["x"] = (el["x"] + c_w / 2.0) - new_w / 2.0
                                    el["y"] = (el["y"] + c_h / 2.0) - new_h / 2.0
                                    el["width"] = new_w
                                    el["height"] = new_h
                            else:
                                wrapped = label

                            target = text(
                                el["x"],
                                el["y"],
                                wrapped,
                                fontSize=f_size,
                                fontFamily=f_fam,
                                **label_style,
                            )
                            if el.get("frameId"):
                                target["frameId"] = el["frameId"]
                            bind_text(target, el)
                            _center_label(target, el)
                            document["elements"].append(target)
                            index[target["id"]] = target
                            label_id = target["id"]
                    elif not label:
                        document["elements"] = [
                            item
                            for item in document["elements"]
                            if item["id"] != target["id"]
                        ]
                        index.pop(target["id"], None)
                        label_id = None
                        target = None
                    else:
                        c_type = el["type"]
                        c_w = float(el.get("width", 100.0))
                        c_h = float(el.get("height", 100.0))
                        f_size = font_size if font_size is not None else target.get("fontSize", 20)
                        f_fam = font_family if font_family is not None else target.get("fontFamily")

                        if font_size is not None:
                            target["fontSize"] = font_size
                        if font_family is not None:
                            target["fontFamily"] = normalize_font_family(font_family)

                        if c_type in ("rectangle", "ellipse", "diamond"):
                            wrapped = wrap_text_to_shape(
                                label, shape=c_type, target_w=c_w, font_size=f_size, font_family=f_fam
                            )
                            target["text"] = target["originalText"] = wrapped
                            tw, th, _ = measure_text_dimensions(
                                wrapped, font_family=target.get("fontFamily"), font_size=target.get("fontSize", 20)
                            )
                            target["width"] = tw
                            target["height"] = th

                            min_w, min_h = required_container_size(c_type, tw, th)

                            if min_w > c_w or min_h > c_h:
                                new_w = max(c_w, min_w)
                                new_h = max(c_h, min_h)
                                el["x"] = (el["x"] + c_w / 2.0) - new_w / 2.0
                                el["y"] = (el["y"] + c_h / 2.0) - new_h / 2.0
                                el["width"] = new_w
                                el["height"] = new_h
                        else:
                            target["text"] = target["originalText"] = label
                            tw, th, _ = measure_text_dimensions(
                                label, font_family=target.get("fontFamily"), font_size=target.get("fontSize", 20)
                            )
                            target["width"] = tw
                            target["height"] = th

                        _center_label(target, el)
                elif target is not None:
                    if font_size is not None:
                        target["fontSize"] = font_size
                    if font_family is not None:
                        target["fontFamily"] = normalize_font_family(font_family)

                    c_type = el.get("type", "rectangle")
                    c_w = float(el.get("width", 100.0))
                    c_h = float(el.get("height", 100.0))
                    if c_type in ("rectangle", "ellipse", "diamond"):
                        wrapped = wrap_text_to_shape(
                            target.get("originalText", target["text"]),
                            shape=c_type,
                            target_w=c_w,
                            font_size=target.get("fontSize", 20),
                            font_family=target.get("fontFamily"),
                        )
                        target["text"] = wrapped
                        tw, th, _ = measure_text_dimensions(
                            wrapped, font_family=target.get("fontFamily"), font_size=target.get("fontSize", 20)
                        )
                        target["width"] = tw
                        target["height"] = th
                        min_w, min_h = required_container_size(c_type, tw, th)

                        if min_w > c_w or min_h > c_h:
                            new_w = max(c_w, min_w)
                            new_h = max(c_h, min_h)
                            el["x"] = (el["x"] + c_w / 2.0) - new_w / 2.0
                            el["y"] = (el["y"] + c_h / 2.0) - new_h / 2.0
                            el["width"] = new_w
                            el["height"] = new_h
                    else:
                        tw, th, _ = measure_text_dimensions(
                            target["text"], font_family=target.get("fontFamily"), font_size=target.get("fontSize", 20)
                        )
                        target["width"] = tw
                        target["height"] = th

                    _center_label(target, el)
                el.update(updates)
                return {
                    "status": "updated",
                    "element_id": element_id,
                    "label_id": label_id,
                }

        return self.state.apply(update)

    def connect(self, source_id, target_id, label="", elbowed=False, **style):
        if source_id == target_id:
            raise SceneError("A connector requires two different elements")

        def add_connection(document):
            index = _active(document)
            source, target = _require(index, source_id), _require(index, target_id)
            if source["type"] not in SHAPES or target["type"] not in SHAPES:
                raise SceneError(
                    "Connectors can target rectangle, ellipse or diamond elements"
                )
            source_node = {
                "shape": source["type"],
                "x": source["x"],
                "y": source["y"],
                "w": source["width"],
                "h": source["height"],
                "angle": source.get("angle", 0),
            }
            target_node = {
                "shape": target["type"],
                "x": target["x"],
                "y": target["y"],
                "w": target["width"],
                "h": target["height"],
                "angle": target.get("angle", 0),
            }
            if elbowed:
                from .routing import route_orthogonal_connector

                shapes = [
                    e
                    for e in index.values()
                    if e["type"] in SHAPES
                    and not e.get("isDeleted")
                    and not ((e.get("customData") or {}).get("type") in ("code_block_header",))
                ]
                pair_arrows = [
                    e
                    for e in index.values()
                    if e["type"] in ("arrow", "line")
                    and not e.get("isDeleted")
                    and {
                        (e.get("startBinding") or {}).get("elementId"),
                        (e.get("endBinding") or {}).get("elementId"),
                    }
                    == {source_id, target_id}
                ]
                slot_offset = len(pair_arrows) * 20.0
                world_pts = route_orthogonal_connector(
                    source,
                    target,
                    obstacles=shapes,
                    clearance=15.0,
                    s_offset=slot_offset,
                    t_offset=slot_offset,
                )
                start = world_pts[0]
                end = world_pts[-1]
                origin_x, origin_y = world_pts[0]
                connector = arrow(origin_x, origin_y, end[0], end[1], elbowed=True, **style)
                connector["points"] = [[pt[0] - origin_x, pt[1] - origin_y] for pt in world_pts]
                all_x = [pt[0] for pt in world_pts]
                all_y = [pt[1] for pt in world_pts]
                connector["width"] = max(all_x) - min(all_x)
                connector["height"] = max(all_y) - min(all_y)
            else:
                start, end = (
                    boundary_point(source_node, target_node, 1),
                    boundary_point(target_node, source_node, -1),
                )
                connector = arrow(*start, *end, elbowed=elbowed, **style)
            connector["startBinding"] = {
                "elementId": source_id,
                "focus": 0,
                "gap": 0,
                "fixedPoint": [0.5, 0.5],
                "mode": "inside",
            }
            connector["endBinding"] = {
                "elementId": target_id,
                "focus": 0,
                "gap": 0,
                "fixedPoint": [0.5, 0.5],
                "mode": "inside",
            }
            document["elements"].append(connector)
            label_id = None
            if label:
                label_el = text(
                    (start[0] + end[0]) / 2,
                    (start[1] + end[1]) / 2,
                    label,
                    fontSize=14,
                    **style,
                )
                bind_text(label_el, connector)
                _center_label(label_el, connector)
                document["elements"].append(label_el)
                label_id = label_el["id"]
            return {
                "arrow_id": connector["id"],
                "label_id": label_id,
                "source_id": source_id,
                "target_id": target_id,
            }

        return self.state.apply(add_connection)

    def save(self, name, overwrite=False):
        document = self.state.document()
        path = save_scene(name, document, overwrite=overwrite)
        return {"path": path, "elements": len(document["elements"]), "status": "saved"}

    def export_scene(self):
        """Export a detached snapshot without filesystem access."""
        return _serialize_for_export(self.state.document())

    def read_saved_scene(self, name):
        return _serialize_for_export(load_scene(name))

    def load(self, name):
        revision = self.state.revision
        document = load_scene(name)
        self.state.replace(document, expected_revision=revision)
        return {
            "loaded": len(document["elements"]),
            "name": name,
            "status": "scene loaded",
        }

    def preview(self, scale=1.0, padding=40, background=True):
        if not _finite_number(scale) or scale < 0.25 or scale > 4.0:
            raise SceneError("scale must be a finite number between 0.25 and 4.0")
        if (
            not isinstance(padding, int)
            or isinstance(padding, bool)
            or padding < 0
            or padding > 200
        ):
            raise SceneError("padding must be an integer between 0 and 200")
        document, _ = self.state.snapshot()
        from .renderer import render_scene_to_png

        return render_scene_to_png(
            document, scale=scale, padding=padding, background=bool(background)
        )

    def export_png(
        self,
        name,
        directory=None,
        scale=1.0,
        padding=40,
        background=True,
        overwrite=False,
    ):
        if not isinstance(name, str) or not name.strip():
            raise SceneError("PNG export name cannot be empty")

        clean_name = name.strip()
        if clean_name.lower().endswith(".png"):
            clean_name = clean_name[:-4].strip()

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", clean_name):
            raise SceneError(
                "Export name must be 1–128 letters, digits, underscores, dots or hyphens, "
                "starting with a letter or digit"
            )

        if not _finite_number(scale) or scale < 0.25 or scale > 4.0:
            raise SceneError("scale must be a finite number between 0.25 and 4.0")

        if (
            not isinstance(padding, int)
            or isinstance(padding, bool)
            or padding < 0
            or padding > 200
        ):
            raise SceneError("padding must be an integer between 0 and 200")

        import tempfile
        from .config import export_directory, scene_directory
        from .renderer import render_scene_image

        if directory is not None:
            if not isinstance(directory, (str, Path)) or not str(directory).strip():
                raise SceneError("directory must be a non-empty string or path")
            target_dir = Path(directory).expanduser()
            if not target_dir.is_absolute():
                target_dir = (Path.cwd() / target_dir).resolve()
            else:
                target_dir = target_dir.resolve()
            allowed_export_roots = [
                export_directory().resolve(),
                Path(scene_directory()).resolve(),
                Path.cwd().resolve(),
                Path(tempfile.gettempdir()).resolve(),
            ]
            if not any(
                target_dir == r or target_dir.is_relative_to(r)
                for r in allowed_export_roots
            ):
                raise SceneError(
                    f"Export directory '{directory}' is outside permitted project, export, and temporary locations"
                )
        else:
            target_dir = export_directory().resolve()

        try:
            target_dir.mkdir(mode=0o755, parents=True, exist_ok=True)
        except OSError as exc:
            raise SceneError(f"Could not create export directory: {exc.strerror}") from exc

        target_file = target_dir / f"{clean_name}.png"

        if target_file.exists():
            if target_file.is_dir() or target_file.is_symlink():
                raise SceneError(
                    "Export destination exists and is not a regular file"
                )
            if not overwrite:
                raise SceneError(
                    f"Export file '{target_file.name}' already exists; use overwrite=true to replace it"
                )

        document, revision = self.state.snapshot()
        png_bytes, width, height = render_scene_image(
            document, scale=scale, padding=padding, background=bool(background)
        )

        temp_name = f".export-{uuid.uuid4().hex}.tmp"
        temp_file = target_dir / temp_name

        try:
            with open(temp_file, "wb") as stream:
                stream.write(png_bytes)
                stream.flush()
                os.fsync(stream.fileno())

            os.replace(temp_file, target_file)
        except OSError as exc:
            try:
                temp_file.unlink(missing_ok=True)
            except Exception:
                pass
            raise SceneError(f"Could not write PNG export: {exc.strerror}") from exc

        return {
            "status": "png exported",
            "name": f"{clean_name}.png",
            "path": str(target_file.resolve()),
            "bytes": len(png_bytes),
            "width": width,
            "height": height,
            "scale": scale,
            "revision": revision,
        }

    def add_code_block(
        self,
        code,
        language="python",
        x=0,
        y=0,
        title=None,
        theme="dark",
        font_size=14,
        font_family="monospace",
        line_numbers=True,
        w=None,
        h=None,
        frame_id=None,
    ):
        if not isinstance(code, str) or not code.strip():
            raise SceneError("code block content cannot be empty")
        if not _finite_number(x) or not _finite_number(y):
            raise SceneError("x and y coordinates must be finite numbers")
        if font_size is not None and (
            not isinstance(font_size, int) or font_size < 8 or font_size > 100
        ):
            raise SceneError("font_size must be an integer between 8 and 100")
        if w is not None and (not _finite_number(w) or w <= 0):
            raise SceneError("w must be a positive finite number")
        if h is not None and (not _finite_number(h) or h <= 0):
            raise SceneError("h must be a positive finite number")

        from .code_blocks import create_code_block

        container, text_el = create_code_block(
            x=x,
            y=y,
            code=code,
            language=language or "python",
            title=title,
            theme=theme or "dark",
            font_size=font_size or 14,
            font_family=font_family or "monospace",
            line_numbers=bool(line_numbers),
            w=w,
            h=h,
            frame_id=frame_id,
        )

        ids = self.state.add_many([container, text_el])
        return {
            "status": "code block created",
            "container_id": ids[0],
            "text_id": ids[1],
            "width": container["width"],
            "height": container["height"],
            "revision": self.state.revision,
        }

    def list_fonts(self, category=None):
        from .fonts import list_fonts as sys_list_fonts

        raw_fonts = sys_list_fonts(category=category)
        defaults = {
            "sans-serif": os.environ.get("EXCALIDRAW_DEFAULT_FONT")
            or "Adwaita Sans / Droid Sans / System Sans",
            "monospace": os.environ.get("EXCALIDRAW_MONO_FONT")
            or "JetBrains Mono / Adwaita Mono / System Mono",
            "handwriting": "Excalifont",
        }
        return {
            "fonts": raw_fonts,
            "total": len(raw_fonts),
            "defaults": defaults,
        }

    def draw_architecture(self, prompt, wrap_threshold=4, **style):
        revision = self.state.revision
        nodes = parse_architecture(prompt)
        if not nodes or any(not node["label"].strip() for node in nodes):
            raise SceneError(
                "Provide at least one nonempty component label, e.g. 'box: API, box: Database'"
            )
        graph_nodes = [{**node, "id": node["id"]} for node in nodes]
        edges = [
            {
                "id": f"edge-{i}",
                "source": nodes[i - 1]["id"],
                "target": nodes[i]["id"],
                "label": "",
            }
            for i in range(1, len(nodes))
        ]
        if len(graph_nodes) > wrap_threshold:
            from .layout import grid_layout
            cols = max(3, math.ceil(math.sqrt(len(graph_nodes) * 1.5)))
            positioned_nodes = grid_layout(graph_nodes, cols=cols, snake=True)
            result = self.draw_graph(
                positioned_nodes,
                edges,
                layout="preset",
                style=style,
                expected_revision=revision,
                font_family=style.get("font_family"),
                font_size=style.get("font_size"),
            )
        else:
            result = self.draw_graph(
                graph_nodes,
                edges,
                layout="horizontal",
                style=style,
                expected_revision=revision,
                font_family=style.get("font_family"),
                font_size=style.get("font_size"),
            )
        self.resolve_layout()
        return {
            **result,
            "url": None,
            "next_step": "Use save(name), export_scene(), or export_to_excalidraw_url() to export or share the document.",
        }

    def add_frame(self, name, x, y, w, h, element_ids=None, **style):
        if (
            not _finite_number(x)
            or not _finite_number(y)
            or not _finite_number(w)
            or not _finite_number(h)
        ):
            raise SceneError("Frame coordinates and dimensions must be finite numbers")
        if w <= 0 or h <= 0:
            raise SceneError("Frame width and height must be positive")
        if not isinstance(name, str):
            raise SceneError("Frame name must be a string")

        def create_frame(document):
            index = _active(document)
            frame_el = frame(x, y, w, h, name=name, **style)
            if element_ids:
                for eid in element_ids:
                    target = _require(index, eid)
                    target["frameId"] = frame_el["id"]
                    lbl = _label_for(index, eid)
                    if lbl:
                        lbl["frameId"] = frame_el["id"]
            document["elements"].insert(0, frame_el)
            return {"frame_id": frame_el["id"]}

        return self.state.apply(create_frame)

    def resolve_layout(
        self,
        min_gap_x: float = 35.0,
        min_gap_y: float = 40.0,
        layer_gap: float = 50.0,
        frame_padding: float = 30.0,
    ):
        """Automatically resolve all component overlaps, expand frames, and align layers."""
        from .layout import resolve_scene_layout

        def apply_resolve(document):
            resolve_scene_layout(
                document,
                min_gap_x=min_gap_x,
                min_gap_y=min_gap_y,
                layer_gap=layer_gap,
                frame_padding=frame_padding,
            )
            return {"status": "layout resolved", "revision": self.state.revision}

        return self.state.apply(apply_resolve)

    def check_geometry(self, min_gap: float = 30.0):
        """Run geometric collision, frame containment, and connector diagnostics on current scene."""
        from .layout import check_diagram_geometry

        doc, revision = self.state.snapshot()
        result = check_diagram_geometry(doc, min_gap=min_gap)
        return {"revision": revision, **result}

    def reroute_connectors(
        self, clearance: float = 15.0, lane_spacing: float = 24.0, only_elbowed: bool = False
    ):
        """Recalculate all connector paths and label positions with obstacle avoidance."""
        from .routing import reroute_scene_arrows

        def apply_reroute(document):
            reroute_scene_arrows(
                document["elements"],
                clearance=clearance,
                lane_spacing=lane_spacing,
                only_elbowed=only_elbowed,
            )
            return {"status": "connectors rerouted", "revision": self.state.revision}

        return self.state.apply(apply_reroute)

    def auto_fix_layout(
        self,
        name: str | None = None,
        dry_run: bool = False,
        repair_scope: str = "all",
        aggressiveness: str = "balanced",
        min_gap: float = 30.0,
    ) -> dict[str, Any]:
        """Diagnose, plan, and automatically repair layout defects with transactional rollback safety.

        min_gap must be between 0 and 1000 (effective spacing defect threshold is min_gap * 0.65).
        aggressiveness="gentle" provides a smaller expansion (0.8x), not compaction.
        """
        from .auto_fix import auto_fix_scene_layout, _validate_params

        if not isinstance(dry_run, bool):
            raise SceneError("dry_run must be a boolean")

        repair_scope, aggressiveness, min_gap = _validate_params(
            repair_scope, aggressiveness, min_gap
        )

        if name is not None:
            if dry_run:
                doc = load_scene(name)
                fix_res = auto_fix_scene_layout(
                    doc,
                    dry_run=True,
                    repair_scope=repair_scope,
                    aggressiveness=aggressiveness,
                    min_gap=float(min_gap),
                )
                fix_res_clean = {k: v for k, v in fix_res.items() if k != "document"}
                return {**fix_res_clean, "revision": self.state.revision}

            def apply_named_fix(active_draft):
                doc = load_scene(name)
                fix_res = auto_fix_scene_layout(
                    doc,
                    dry_run=False,
                    repair_scope=repair_scope,
                    aggressiveness=aggressiveness,
                    min_gap=float(min_gap),
                )
                if (
                    not fix_res.get("rolled_back")
                    and fix_res.get("status") in ("repaired", "partially_repaired")
                ):
                    save_scene(name, fix_res["document"], overwrite=True)
                    active_draft["elements"] = fix_res["document"]["elements"]
                    if "appState" in fix_res.get("document", {}):
                        active_draft["appState"] = fix_res["document"]["appState"]
                return fix_res

            fix_res = self.state.apply(apply_named_fix)
            fix_res_clean = {k: v for k, v in fix_res.items() if k != "document"}
            return {**fix_res_clean, "revision": self.state.revision}

        if dry_run:
            doc, rev = self.state.snapshot()
            fix_res = auto_fix_scene_layout(
                doc,
                dry_run=True,
                repair_scope=repair_scope,
                aggressiveness=aggressiveness,
                min_gap=float(min_gap),
            )
            fix_res_clean = {k: v for k, v in fix_res.items() if k != "document"}
            return {**fix_res_clean, "revision": rev}

        def apply_fix(doc):
            fix_res = auto_fix_scene_layout(
                doc,
                dry_run=False,
                repair_scope=repair_scope,
                aggressiveness=aggressiveness,
                min_gap=float(min_gap),
            )
            if (
                not fix_res.get("rolled_back")
                and fix_res.get("status") in ("repaired", "partially_repaired")
            ):
                doc["elements"] = fix_res["document"]["elements"]
                if "appState" in fix_res.get("document", {}):
                    doc["appState"] = fix_res["document"]["appState"]
            return fix_res

        fix_res = self.state.apply(apply_fix)
        fix_res_clean = {k: v for k, v in fix_res.items() if k != "document"}
        return {**fix_res_clean, "revision": self.state.revision}

    def find_elements(
        self,
        query=None,
        type=None,
        frame_id=None,
        element_id=None,
        connected_to=None,
        include_bound_labels=False,
        limit=50,
    ):
        if (
            limit is not None
            and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 200)
        ):
            raise SceneError("limit must be an integer between 1 and 200")

        document, revision = self.state.snapshot()
        active = [el for el in document["elements"] if not el.get("isDeleted")]
        index = {el["id"]: el for el in active}

        connected_ids = set()
        if connected_to:
            if connected_to not in index:
                raise SceneError(f"Element '{connected_to}' not found")
            for el in active:
                if el["type"] == "arrow":
                    sb = (el.get("startBinding") or {}).get("elementId")
                    eb = (el.get("endBinding") or {}).get("elementId")
                    if sb == connected_to or eb == connected_to:
                        connected_ids.add(el["id"])
                        if sb and sb != connected_to:
                            connected_ids.add(sb)
                        if eb and eb != connected_to:
                            connected_ids.add(eb)

        matches = []
        q_lower = (
            query.strip().lower()
            if (isinstance(query, str) and query.strip())
            else None
        )

        for el in active:
            eid = el["id"]
            etype = el["type"]

            if not include_bound_labels and el.get("containerId") and element_id != eid:
                continue

            if element_id and eid != element_id:
                continue

            if type and etype != type:
                continue

            if frame_id is not None:
                if el.get("frameId") != frame_id:
                    continue

            if connected_to:
                if eid not in connected_ids:
                    continue

            label_el = _label_for(index, eid)
            label_text = (
                label_el.get("text")
                if label_el
                else (el.get("text") if etype == "text" else None)
            )
            frame_name = el.get("name") if etype == "frame" else None

            if q_lower:
                matched_query = False
                if label_text and q_lower in label_text.lower():
                    matched_query = True
                elif frame_name and q_lower in frame_name.lower():
                    matched_query = True
                elif q_lower in eid.lower():
                    matched_query = True
                if not matched_query:
                    continue

            bound_elements = el.get("boundElements") or []
            bound_ids = [
                b["id"]
                for b in bound_elements
                if isinstance(b, dict) and b.get("id")
            ]

            summary = {
                "id": eid,
                "type": etype,
                "x": float(el["x"]),
                "y": float(el["y"]),
                "width": float(el.get("width", 0)),
                "height": float(el.get("height", 0)),
                "bound_element_ids": bound_ids,
            }
            if label_text is not None:
                summary["label"] = label_text
            if frame_name is not None:
                summary["name"] = frame_name
            if el.get("frameId"):
                summary["frame_id"] = el["frameId"]
            if el.get("containerId"):
                summary["container_id"] = el["containerId"]
            if el.get("strokeColor"):
                summary["stroke_color"] = el["strokeColor"]
            if el.get("backgroundColor"):
                summary["background_color"] = el["backgroundColor"]

            matches.append(summary)

        return {
            "total": len(matches),
            "matches": matches[:limit],
            "revision": revision,
        }

    def batch_mutate(self, operations, auto_layout: bool = False):
        if not isinstance(operations, list) or not operations:
            raise SceneError("Operations must be a non-empty list")
        if len(operations) > 500:
            raise SceneError("Batch is limited to 500 operations")

        def execute_batch(document):
            index = _active(document)
            ref_map = {}
            results = []

            def resolve(val):
                if isinstance(val, str):
                    if val in ref_map:
                        return ref_map[val]
                    if val.startswith("client:") and val[7:] in ref_map:
                        return ref_map[val[7:]]
                return val

            def resolve_list(vals):
                if isinstance(vals, list):
                    return [resolve(v) for v in vals]
                return vals

            for i, raw_op in enumerate(operations):
                op = raw_op if isinstance(raw_op, dict) else raw_op.model_dump()
                action = op.get("action")
                if not action:
                    raise SceneError(f"Operation at index {i} is missing 'action'")

                client_id = op.get("client_id")

                if action in ("add_rectangle", "add_circle", "add_diamond"):
                    shape = {
                        "add_rectangle": "rectangle",
                        "add_circle": "ellipse",
                        "add_diamond": "diamond",
                    }[action]
                    x = op.get("x")
                    y = op.get("y")
                    w = (
                        op.get("w")
                        if op.get("w") is not None
                        else op.get("width", op.get("size"))
                    )
                    h = (
                        op.get("h")
                        if op.get("h") is not None
                        else op.get("height", op.get("size"))
                    )
                    if shape == "ellipse" and op.get("size") is not None:
                        w = h = op.get("size")
                    if (
                        not _finite_number(x)
                        or not _finite_number(y)
                        or not _finite_number(w)
                        or not _finite_number(h)
                    ):
                        raise SceneError(
                            f"Operation {i} ({action}): coordinates and dimensions must be finite numbers"
                        )
                    if w <= 0 or h <= 0:
                        raise SceneError(
                            f"Operation {i} ({action}): dimensions must be positive"
                        )
                    style = {
                        k: v
                        for k, v in op.items()
                        if k
                        in (
                            "strokeColor",
                            "backgroundColor",
                            "fillStyle",
                            "strokeWidth",
                            "strokeStyle",
                            "opacity",
                            "roughness",
                            "roundness",
                        )
                        and v is not None
                    }
                    frame_id = resolve(op.get("frame_id"))
                    if frame_id:
                        _require(index, frame_id)
                    els = _shape_elements(
                        shape,
                        x,
                        y,
                        w,
                        h,
                        op.get("label", ""),
                        style,
                        frame_id=frame_id,
                    )
                    for el in els:
                        document["elements"].append(el)
                        index[el["id"]] = el
                    key = {
                        "rectangle": "rectangle_id",
                        "ellipse": "circle_id",
                        "diamond": "diamond_id",
                    }[shape]
                    res = {
                        "action": action,
                        key: els[0]["id"],
                        "label_id": els[1]["id"] if len(els) > 1 else None,
                    }
                    if client_id:
                        ref_map[client_id] = els[0]["id"]
                    results.append(res)

                elif action == "add_frame":
                    x = op.get("x")
                    y = op.get("y")
                    w = (
                        op.get("w")
                        if op.get("w") is not None
                        else op.get("width")
                    )
                    h = (
                        op.get("h")
                        if op.get("h") is not None
                        else op.get("height")
                    )
                    name = op.get("name", "")
                    if (
                        not _finite_number(x)
                        or not _finite_number(y)
                        or not _finite_number(w)
                        or not _finite_number(h)
                    ):
                        raise SceneError(
                            f"Operation {i} (add_frame): coordinates and dimensions must be finite numbers"
                        )
                    if w <= 0 or h <= 0:
                        raise SceneError(
                            f"Operation {i} (add_frame): width and height must be positive"
                        )
                    style = {
                        k: v
                        for k, v in op.items()
                        if k
                        in (
                            "strokeColor",
                            "backgroundColor",
                            "fillStyle",
                            "strokeWidth",
                            "strokeStyle",
                            "opacity",
                            "roughness",
                        )
                        and v is not None
                    }
                    frame_el = frame(x, y, w, h, name=name, **style)
                    eids = resolve_list(op.get("element_ids"))
                    if eids:
                        for eid in eids:
                            target = _require(index, eid)
                            target["frameId"] = frame_el["id"]
                            lbl = _label_for(index, eid)
                            if lbl:
                                lbl["frameId"] = frame_el["id"]
                    document["elements"].insert(0, frame_el)
                    index[frame_el["id"]] = frame_el
                    res = {"action": "add_frame", "frame_id": frame_el["id"]}
                    if client_id:
                        ref_map[client_id] = frame_el["id"]
                    results.append(res)

                elif action == "add_arrow":
                    x, y = op.get("x"), op.get("y")
                    x2, y2 = op.get("x2"), op.get("y2")
                    if not all(_finite_number(v) for v in (x, y, x2, y2)):
                        raise SceneError(
                            f"Operation {i} (add_arrow): points must be finite numbers"
                        )
                    elbowed = op.get("elbowed", False)
                    style = {
                        k: v
                        for k, v in op.items()
                        if k
                        in (
                            "strokeColor",
                            "strokeWidth",
                            "strokeStyle",
                            "opacity",
                            "roughness",
                        )
                        and v is not None
                    }
                    arrow_el = arrow(x, y, x2, y2, elbowed=elbowed, **style)
                    els = [arrow_el]
                    lbl_text = op.get("label", "")
                    if lbl_text:
                        lbl_el = text(x, y, lbl_text, fontSize=14, **style)
                        bind_text(lbl_el, arrow_el)
                        _center_label(lbl_el, arrow_el)
                        els.append(lbl_el)
                    for el in els:
                        document["elements"].append(el)
                        index[el["id"]] = el
                    res = {
                        "action": "add_arrow",
                        "arrow_id": arrow_el["id"],
                        "label_id": els[1]["id"] if len(els) > 1 else None,
                    }
                    if client_id:
                        ref_map[client_id] = arrow_el["id"]
                    results.append(res)

                elif action == "add_text":
                    x, y = op.get("x"), op.get("y")
                    content = op.get("content")
                    if not _finite_number(x) or not _finite_number(y):
                        raise SceneError(
                            f"Operation {i} (add_text): coordinates must be finite numbers"
                        )
                    if not isinstance(content, str) or not content.strip():
                        raise SceneError(
                            f"Operation {i} (add_text): content cannot be empty"
                        )
                    font_size = op.get("font_size", 20)
                    font_family = op.get("font_family")
                    style = {
                        k: v
                        for k, v in op.items()
                        if k in ("strokeColor", "opacity") and v is not None
                    }
                    frame_id = resolve(op.get("frame_id"))
                    if frame_id:
                        _require(index, frame_id)
                        style["frameId"] = frame_id
                    txt_el = text(
                        x,
                        y,
                        content,
                        fontSize=font_size,
                        fontFamily=font_family or 2,
                        **style,
                    )
                    document["elements"].append(txt_el)
                    index[txt_el["id"]] = txt_el
                    res = {"action": "add_text", "text_id": txt_el["id"]}
                    if client_id:
                        ref_map[client_id] = txt_el["id"]
                    results.append(res)

                elif action == "add_code_block":
                    code = op.get("code")
                    if not isinstance(code, str) or not code.strip():
                        raise SceneError(
                            f"Operation {i} (add_code_block): code cannot be empty"
                        )
                    x = op.get("x", 0)
                    y = op.get("y", 0)
                    if not _finite_number(x) or not _finite_number(y):
                        raise SceneError(
                            f"Operation {i} (add_code_block): coordinates must be finite numbers"
                        )
                    lang = op.get("language", "python")
                    title = op.get("title")
                    theme = op.get("theme", "dark")
                    f_size = op.get("font_size", 14)
                    f_fam = op.get("font_family", "monospace")
                    ln = op.get("line_numbers", True)
                    w = op.get("w")
                    h = op.get("h")
                    fid = resolve(op.get("frame_id"))
                    from .code_blocks import create_code_block

                    c_box, c_txt = create_code_block(
                        x=x,
                        y=y,
                        code=code,
                        language=lang,
                        title=title,
                        theme=theme,
                        font_size=f_size,
                        font_family=f_fam,
                        line_numbers=ln,
                        w=w,
                        h=h,
                        frame_id=fid,
                    )
                    document["elements"].extend([c_box, c_txt])
                    index[c_box["id"]] = c_box
                    index[c_txt["id"]] = c_txt
                    res = {
                        "action": "add_code_block",
                        "container_id": c_box["id"],
                        "text_id": c_txt["id"],
                    }
                    if client_id:
                        ref_map[client_id] = c_box["id"]
                    results.append(res)

                elif action == "connect":
                    source_id = resolve(op.get("source_id"))
                    target_id = resolve(op.get("target_id"))
                    if not source_id or not target_id:
                        raise SceneError(
                            f"Operation {i} (connect): source_id and target_id are required"
                        )
                    if source_id == target_id:
                        raise SceneError(
                            f"Operation {i} (connect): source and target must differ"
                        )
                    source = _require(index, source_id)
                    target = _require(index, target_id)
                    if source["type"] not in SHAPES or target["type"] not in SHAPES:
                        raise SceneError(
                            f"Operation {i} (connect): connectors can target rectangle, ellipse or diamond elements"
                        )
                    source_node = {
                        "shape": source["type"],
                        "x": source["x"],
                        "y": source["y"],
                        "w": source["width"],
                        "h": source["height"],
                        "angle": source.get("angle", 0),
                    }
                    target_node = {
                        "shape": target["type"],
                        "x": target["x"],
                        "y": target["y"],
                        "w": target["width"],
                        "h": target["height"],
                        "angle": target.get("angle", 0),
                    }
                    start = boundary_point(source_node, target_node, 1)
                    end = boundary_point(target_node, source_node, -1)
                    elbowed = op.get("elbowed", False)
                    style = {
                        k: v
                        for k, v in op.items()
                        if k
                        in (
                            "strokeColor",
                            "strokeWidth",
                            "strokeStyle",
                            "opacity",
                            "roughness",
                        )
                        and v is not None
                    }
                    connector = arrow(*start, *end, elbowed=elbowed, **style)
                    connector["startBinding"] = {
                        "elementId": source_id,
                        "focus": 0,
                        "gap": 0,
                        "fixedPoint": [0.5, 0.5],
                        "mode": "inside",
                    }
                    connector["endBinding"] = {
                        "elementId": target_id,
                        "focus": 0,
                        "gap": 0,
                        "fixedPoint": [0.5, 0.5],
                        "mode": "inside",
                    }
                    document["elements"].append(connector)
                    index[connector["id"]] = connector
                    lbl_id = None
                    label = op.get("label", "")
                    if label:
                        label_el = text(
                            (start[0] + end[0]) / 2,
                            (start[1] + end[1]) / 2,
                            label,
                            fontSize=14,
                            **style,
                        )
                        bind_text(label_el, connector)
                        _center_label(label_el, connector)
                        document["elements"].append(label_el)
                        index[label_el["id"]] = label_el
                        lbl_id = label_el["id"]
                    res = {
                        "action": "connect",
                        "arrow_id": connector["id"],
                        "label_id": lbl_id,
                        "source_id": source_id,
                        "target_id": target_id,
                    }
                    if client_id:
                        ref_map[client_id] = connector["id"]
                    results.append(res)

                elif action == "move":
                    eid = resolve(op.get("element_id"))
                    x, y = op.get("x"), op.get("y")
                    if not eid or not _finite_number(x) or not _finite_number(y):
                        raise SceneError(
                            f"Operation {i} (move): element_id, finite x and y are required"
                        )
                    el = _require(index, eid)
                    if el.get("locked"):
                        raise SceneError(
                            f"Operation {i} (move): cannot move locked element '{eid}'"
                        )
                    if el.get("containerId"):
                        raise SceneError(
                            "Move the label's container instead of moving bound text independently"
                        )
                    dx, dy = x - el["x"], y - el["y"]
                    if dx or dy:
                        if el["type"] == "arrow" and el.get("elbowed"):
                            raise SceneError(
                                "Moving elbowed arrows is not supported yet"
                            )
                        grouped_members = []
                        if el.get("groupIds"):
                            target_groups = set(el["groupIds"])
                            for other in index.values():
                                if other["id"] != eid and any(
                                    g in target_groups for g in other.get("groupIds", [])
                                ):
                                    if other.get("locked"):
                                        raise SceneError(
                                            f"Operation {i} (move): cannot move locked element '{other['id']}' in group"
                                        )
                                    grouped_members.append(other)
                        _translate(el, dx, dy)
                        moved_targets = {eid}
                        owned_labels = {
                            lbl["containerId"]: lbl
                            for lbl in index.values()
                            if lbl.get("containerId")
                        }
                        for member in grouped_members:
                            _translate(member, dx, dy)
                            moved_targets.add(member["id"])
                        if el["type"] == "frame":
                            for child in index.values():
                                if child.get("frameId") == eid:
                                    if child.get("locked"):
                                        raise SceneError(
                                            f"Operation {i} (move): cannot move locked element '{child['id']}' in frame"
                                        )
                                    _translate(child, dx, dy)
                                    moved_targets.add(child["id"])
                        for lbl in index.values():
                            if lbl.get("containerId") in moved_targets:
                                _translate(lbl, dx, dy)
                                moved_targets.add(lbl["id"])
                        if el["type"] == "arrow":
                            el["startBinding"] = None
                            el["endBinding"] = None
                        for conn in index.values():
                            if conn["type"] != "arrow" or conn["id"] in moved_targets:
                                continue
                            start = (
                                (conn.get("startBinding") or {}).get("elementId")
                                in moved_targets
                            )
                            end = (
                                (conn.get("endBinding") or {}).get("elementId")
                                in moved_targets
                            )
                            if start or end:
                                _move_arrow_endpoints(conn, dx, dy, start, end)
                                lbl = owned_labels.get(conn["id"])
                                if lbl:
                                    _translate(
                                        lbl,
                                        dx * (int(start) + int(end)) / 2,
                                        dy * (int(start) + int(end)) / 2,
                                    )
                    results.append(
                        {
                            "action": "move",
                            "status": "moved",
                            "element_id": eid,
                            "x": x,
                            "y": y,
                        }
                    )

                elif action == "resize":
                    eid = resolve(op.get("element_id"))
                    w = (
                        op.get("w")
                        if op.get("w") is not None
                        else op.get("width")
                    )
                    h = (
                        op.get("h")
                        if op.get("h") is not None
                        else op.get("height")
                    )
                    if (
                        not eid
                        or not _finite_number(w)
                        or not _finite_number(h)
                        or w <= 0
                        or h <= 0
                    ):
                        raise SceneError(
                            f"Operation {i} (resize): element_id, positive width and height required"
                        )
                    el = _require(index, eid)
                    if el.get("locked"):
                        raise SceneError(
                            f"Operation {i} (resize): cannot resize locked element '{eid}'"
                        )
                    if el["type"] not in (*SHAPES, "frame"):
                        raise SceneError(
                            f"Operation {i} (resize): only rectangle, ellipse, diamond, frame can be resized"
                        )
                    el["width"], el["height"] = w, h
                    lbl = _label_for(index, eid)
                    if lbl:
                        _center_label(lbl, el)
                    for conn in index.values():
                        if conn["type"] == "arrow" and any(
                            (conn.get(end) or {}).get("elementId") == eid
                            for end in ("startBinding", "endBinding")
                        ):
                            _reroute_connector(index, conn)
                    results.append(
                        {
                            "action": "resize",
                            "status": "resized",
                            "element_id": eid,
                            "width": w,
                            "height": h,
                        }
                    )

                elif action == "update_element":
                    eid = resolve(op.get("element_id"))
                    if not eid:
                        raise SceneError(
                            f"Operation {i} (update_element): element_id is required"
                        )
                    el = _require(index, eid)
                    if el.get("locked"):
                        raise SceneError(
                            f"Operation {i} (update_element): cannot update locked element '{eid}'"
                        )
                    label = op.get("label")
                    f_fam = op.get("font_family")
                    f_size = op.get("font_size")
                    style_keys = (
                        "strokeColor",
                        "backgroundColor",
                        "fillStyle",
                        "strokeWidth",
                        "strokeStyle",
                        "opacity",
                        "roughness",
                    )
                    updates = {
                        k: op[k] for k in style_keys if op.get(k) is not None
                    }
                    if op.get("roundness") is not None:
                        r = op["roundness"]
                        if r == "adaptive":
                            updates["roundness"] = {"type": 3}
                        elif r == "round":
                            updates["roundness"] = {"type": 2}
                        elif r == "sharp":
                            updates["roundness"] = None
                        elif isinstance(r, dict):
                            updates["roundness"] = r
                    if op.get("elbowed") is not None:
                        updates["elbowed"] = bool(op["elbowed"])
                    target_frame_id = resolve(op.get("frame_id"))
                    if target_frame_id is not None:
                        if target_frame_id == "":
                            el["frameId"] = None
                            tgt_lbl = _label_for(index, eid)
                            if tgt_lbl:
                                tgt_lbl["frameId"] = None
                        else:
                            _require(index, target_frame_id)
                            el["frameId"] = target_frame_id
                            tgt_lbl = _label_for(index, eid)
                            if tgt_lbl:
                                tgt_lbl["frameId"] = target_frame_id
                    if el["type"] == "frame" and label is not None:
                        el["name"] = label
                    elif el["type"] == "text":
                        cid = el.get("containerId")
                        container = index.get(cid) if cid else None
                        if f_fam is not None:
                            el["fontFamily"] = normalize_font_family(f_fam)
                            if isinstance(f_fam, str) and f_fam.strip().lower() not in (
                                "1",
                                "2",
                                "3",
                                "4",
                                "excalifont",
                                "virgil",
                                "sans-serif",
                                "sans",
                                "helvetica",
                                "normal",
                                "monospace",
                                "mono",
                                "code",
                                "cascadia",
                                "comic-shanns",
                                "comic",
                                "comic shanns",
                                "handwriting",
                                "hand-drawn",
                                "hand",
                            ):
                                el.setdefault("customData", {})["fontFamily"] = f_fam.strip()
                            elif "customData" in el and "fontFamily" in el["customData"]:
                                el["customData"]["fontFamily"] = str(f_fam)
                        if f_size is not None:
                            el["fontSize"] = f_size
                            lines = el["text"].split("\n")
                            el["width"] = max(map(len, lines)) * el["fontSize"] * 0.6
                            el["height"] = len(lines) * el["fontSize"] * el.get("lineHeight", 1.25)
                            if container:
                                _center_label(el, container)
                        if label is not None:
                            if not label:
                                if container is None:
                                    raise SceneError(
                                        "Standalone text cannot be empty; use delete instead"
                                    )
                                document["elements"] = [
                                    item
                                    for item in document["elements"]
                                    if item["id"] != el["id"]
                                ]
                                index.pop(el["id"], None)
                            else:
                                el["text"] = el["originalText"] = label
                                el["width"] = (
                                    max(map(len, label.split("\n")))
                                    * el["fontSize"]
                                    * 0.6
                                )
                                el["height"] = (
                                    len(label.split("\n"))
                                    * el["fontSize"]
                                    * el["lineHeight"]
                                )
                                if container:
                                    _center_label(el, container)
                        el.update(updates)
                    else:
                        target = _label_for(index, eid)
                        if label is not None:
                            if target is None and label:
                                lbl_style = {
                                    "strokeColor": updates.get(
                                        "strokeColor",
                                        el.get("strokeColor", "#1e1e1e"),
                                    ),
                                    "opacity": updates.get(
                                        "opacity", el.get("opacity", 100)
                                    ),
                                }
                                fs = f_size if f_size is not None else (14 if el["type"] == "arrow" else 20)
                                target = text(
                                    el["x"],
                                    el["y"],
                                    label,
                                    fontSize=fs,
                                    fontFamily=f_fam or 2,
                                    **lbl_style,
                                )
                                if el.get("frameId"):
                                    target["frameId"] = el["frameId"]
                                bind_text(target, el)
                                _center_label(target, el)
                                document["elements"].append(target)
                                index[target["id"]] = target
                            elif target is not None and not label:
                                document["elements"] = [
                                    item
                                    for item in document["elements"]
                                    if item["id"] != target["id"]
                                ]
                                index.pop(target["id"], None)
                            elif target is not None:
                                target["text"] = target["originalText"] = label
                                if f_size is not None:
                                    target["fontSize"] = f_size
                                if f_fam is not None:
                                    target["fontFamily"] = normalize_font_family(f_fam)
                                target["width"] = (
                                    max(map(len, label.split("\n")))
                                    * target["fontSize"]
                                    * 0.6
                                )
                                target["height"] = (
                                    len(label.split("\n"))
                                    * target["fontSize"]
                                    * target["lineHeight"]
                                )
                                _center_label(target, el)
                        elif target is not None:
                            if f_size is not None:
                                target["fontSize"] = f_size
                            if f_fam is not None:
                                target["fontFamily"] = normalize_font_family(f_fam)
                            lines = target["text"].split("\n")
                            target["width"] = max(map(len, lines)) * target["fontSize"] * 0.6
                            target["height"] = len(lines) * target["fontSize"] * target.get("lineHeight", 1.25)
                            _center_label(target, el)
                        el.update(updates)
                    results.append(
                        {
                            "action": "update_element",
                            "status": "updated",
                            "element_id": eid,
                        }
                    )

                elif action == "delete":
                    eid = resolve(op.get("element_id"))
                    if not eid:
                        raise SceneError(
                            f"Operation {i} (delete): element_id is required"
                        )
                    el = _require(index, eid)
                    if el.get("locked"):
                        raise SceneError(
                            f"Operation {i} (delete): cannot delete locked element '{eid}'"
                        )
                    removed = {eid}
                    removed.update(
                        el["id"]
                        for el in index.values()
                        if el.get("containerId") == eid
                    )
                    document["elements"] = [
                        el
                        for el in document["elements"]
                        if el["id"] not in removed
                    ]
                    for el in document["elements"]:
                        if el.get("frameId") == eid:
                            el["frameId"] = None
                        if el["type"] == "arrow" and not el.get("isDeleted"):
                            for end in ("startBinding", "endBinding"):
                                if (el.get(end) or {}).get("elementId") in removed:
                                    el[end] = None
                    for r in removed:
                        index.pop(r, None)
                    results.append(
                        {
                            "action": "delete",
                            "status": "deleted",
                            "element_id": eid,
                        }
                    )

                elif action == "lock":
                    eids = resolve_list(op.get("element_ids")) or (
                        [resolve(op.get("element_id"))] if op.get("element_id") else []
                    )
                    if not eids:
                        raise SceneError(
                            f"Operation {i} (lock): element_ids or element_id required"
                        )
                    locked_ids = []
                    for target_eid in eids:
                        el = _require(index, target_eid)
                        el["locked"] = True
                        locked_ids.append(target_eid)
                        lbl = _label_for(index, target_eid)
                        if lbl:
                            lbl["locked"] = True
                            locked_ids.append(lbl["id"])
                    results.append(
                        {
                            "action": "lock",
                            "status": "locked",
                            "element_ids": locked_ids,
                        }
                    )

                elif action == "unlock":
                    eids = resolve_list(op.get("element_ids")) or (
                        [resolve(op.get("element_id"))] if op.get("element_id") else []
                    )
                    if not eids:
                        raise SceneError(
                            f"Operation {i} (unlock): element_ids or element_id required"
                        )
                    unlocked_ids = []
                    for target_eid in eids:
                        el = _require(index, target_eid)
                        el["locked"] = False
                        unlocked_ids.append(target_eid)
                        lbl = _label_for(index, target_eid)
                        if lbl:
                            lbl["locked"] = False
                            unlocked_ids.append(lbl["id"])
                    results.append(
                        {
                            "action": "unlock",
                            "status": "unlocked",
                            "element_ids": unlocked_ids,
                        }
                    )

                elif action == "group":
                    import uuid

                    eids = resolve_list(op.get("element_ids"))
                    if not eids or len(eids) < 2:
                        raise SceneError(
                            f"Operation {i} (group): requires at least 2 element IDs"
                        )
                    for target_eid in eids:
                        _require(index, target_eid)
                    gid = f"grp_{uuid.uuid4().hex[:12]}"
                    for target_eid in eids:
                        el = index[target_eid]
                        grps = el.setdefault("groupIds", [])
                        if gid not in grps:
                            grps.append(gid)
                        lbl = _label_for(index, target_eid)
                        if lbl:
                            lbl_grps = lbl.setdefault("groupIds", [])
                            if gid not in lbl_grps:
                                lbl_grps.append(gid)
                    results.append(
                        {
                            "action": "group",
                            "status": "grouped",
                            "group_id": gid,
                            "element_ids": eids,
                        }
                    )

                elif action == "ungroup":
                    target_gid = op.get("group_id")
                    eids = resolve_list(op.get("element_ids"))
                    if not target_gid and not eids:
                        raise SceneError(
                            f"Operation {i} (ungroup): group_id or element_ids required"
                        )
                    affected = set()
                    removed_groups = set()
                    if target_gid:
                        removed_groups.add(target_gid)
                        for el in index.values():
                            grps = el.get("groupIds", [])
                            if target_gid in grps:
                                el["groupIds"] = [g for g in grps if g != target_gid]
                                affected.add(el["id"])
                    if eids:
                        for target_eid in eids:
                            el = _require(index, target_eid)
                            grps = el.get("groupIds", [])
                            if grps:
                                p = grps.pop()
                                removed_groups.add(p)
                                affected.add(target_eid)
                                lbl = _label_for(index, target_eid)
                                if lbl:
                                    lbl_grps = lbl.get("groupIds", [])
                                    if p in lbl_grps:
                                        lbl["groupIds"] = [
                                            g for g in lbl_grps if g != p
                                        ]
                                        affected.add(lbl["id"])
                    results.append(
                        {
                            "action": "ungroup",
                            "status": "ungrouped",
                            "affected_elements": sorted(affected),
                            "removed_group_ids": sorted(removed_groups),
                        }
                    )

                elif action in ("duplicate", "duplicate_elements"):
                    import random
                    import uuid
                    from copy import deepcopy

                    raw_eids = op.get("element_ids") or (
                        [op.get("element_id")] if op.get("element_id") else None
                    )
                    eids = resolve_list(raw_eids)
                    if not eids:
                        raise SceneError(
                            f"Operation {i} ({action}): element_ids must be a non-empty list of IDs"
                        )
                    offset_x = float(op.get("offset_x", 20.0))
                    offset_y = float(op.get("offset_y", 20.0))
                    for target_eid in eids:
                        _require(index, target_eid)

                    targets_set = list(eids)
                    for target_eid in eids:
                        lbl = _label_for(index, target_eid)
                        if lbl and lbl["id"] not in targets_set:
                            targets_set.append(lbl["id"])

                    dup_id_map = {
                        old_id: f"{index[old_id]['type']}_{uuid.uuid4().hex[:10]}"
                        for old_id in targets_set
                    }
                    dup_group_map = {}
                    for old_id in targets_set:
                        for gid in index[old_id].get("groupIds", []):
                            if gid not in dup_group_map:
                                dup_group_map[gid] = f"grp_{uuid.uuid4().hex[:12]}"

                    for old_id in targets_set:
                        orig = index[old_id]
                        cloned = deepcopy(orig)
                        cloned["id"] = dup_id_map[old_id]
                        cloned["x"] += offset_x
                        cloned["y"] += offset_y
                        cloned["seed"] = random.randrange(1, 2**31)
                        cloned["versionNonce"] = random.randrange(1, 2**31)
                        cloned["version"] = 1
                        cloned["locked"] = False

                        if cloned.get("containerId") and cloned["containerId"] in dup_id_map:
                            cloned["containerId"] = dup_id_map[cloned["containerId"]]
                        elif cloned.get("containerId"):
                            cloned["containerId"] = None

                        if cloned.get("frameId") and cloned["frameId"] in dup_id_map:
                            cloned["frameId"] = dup_id_map[cloned["frameId"]]
                        elif cloned.get("frameId") and cloned["frameId"] not in index:
                            cloned["frameId"] = None

                        if cloned.get("boundElements"):
                            cloned["boundElements"] = [
                                {**b, "id": dup_id_map[b["id"]]}
                                for b in cloned["boundElements"]
                                if b["id"] in dup_id_map
                            ]

                        if cloned.get("groupIds"):
                            cloned["groupIds"] = [
                                dup_group_map[gid]
                                for gid in cloned["groupIds"]
                                if gid in dup_group_map
                            ]

                        if cloned.get("type") == "arrow":
                            for end in ("startBinding", "endBinding"):
                                binding = cloned.get(end)
                                if binding:
                                    src_id = binding.get("elementId")
                                    if src_id in dup_id_map:
                                        binding["elementId"] = dup_id_map[src_id]
                                    else:
                                        cloned[end] = None

                        index[cloned["id"]] = cloned
                        document["elements"].append(cloned)

                    duplicated_ids = [dup_id_map[eid] for eid in eids]
                    if client_id:
                        ref_map[client_id] = duplicated_ids[0]
                    results.append(
                        {
                            "action": action,
                            "status": "duplicated",
                            "original_ids": eids,
                            "duplicated_ids": duplicated_ids,
                            "id_mapping": dup_id_map,
                        }
                    )

                elif action == "resolve_layout":
                    from .layout import resolve_scene_layout
                    resolve_scene_layout(
                        document,
                        min_gap_x=op.get("min_gap_x", 35.0),
                        min_gap_y=op.get("min_gap_y", 40.0),
                        layer_gap=op.get("layer_gap", 50.0),
                        frame_padding=op.get("frame_padding", 30.0),
                    )
                    results.append({"action": "resolve_layout", "status": "resolved"})

                elif action == "auto_fix_layout":
                    from .auto_fix import auto_fix_scene_layout

                    min_g = op.get("min_gap")
                    if min_g is None:
                        min_g = op.get("min_gap_x")
                    if min_g is None:
                        min_g = 30.0

                    if not _finite_number(min_g) or min_g < 0:
                        raise SceneError(
                            f"Operation {i} (auto_fix_layout): min_gap must be a non-negative finite number"
                        )

                    d_run = op.get("dry_run", False)
                    if not isinstance(d_run, bool):
                        raise SceneError(
                            f"Operation {i} (auto_fix_layout): dry_run must be a boolean"
                        )

                    fix_res = auto_fix_scene_layout(
                        document,
                        dry_run=d_run,
                        repair_scope=op.get("repair_scope", "all") or "all",
                        aggressiveness=op.get("aggressiveness", "balanced") or "balanced",
                        min_gap=float(min_g),
                    )
                    if not fix_res.get("dry_run") and not fix_res.get("rolled_back"):
                        document["elements"] = fix_res["document"]["elements"]
                        if "appState" in fix_res.get("document", {}):
                            document["appState"] = fix_res["document"]["appState"]
                        index.clear()
                        index.update(
                            {el["id"]: el for el in document["elements"] if el.get("id")}
                        )
                    fix_res_clean = {k: v for k, v in fix_res.items() if k != "document"}
                    results.append({"action": "auto_fix_layout", **fix_res_clean})

                else:
                    raise SceneError(f"Unknown action '{action}' at operation {i}")

            if auto_layout:
                from .layout import resolve_scene_layout
                resolve_scene_layout(document)

            return {
                "status": "batch executed",
                "operations_executed": len(results),
                "results": results,
                "ref_map": ref_map,
            }

        result = self.state.apply(execute_batch)
        return {**result, "revision": self.state.revision}

    def draw_graph(
        self,
        nodes,
        edges,
        clusters=None,
        layout="layered",
        direction="horizontal",
        elbowed=False,
        roundness=None,
        style=None,
        expected_revision=None,
        font_family=None,
        font_size=None,
        cycle_fallback=False,
    ):
        style = dict(style or {})
        if roundness is not None:
            style["roundness"] = roundness
        if font_family is not None:
            style["font_family"] = font_family
        if font_size is not None:
            style["font_size"] = font_size
        revision = (
            self.state.revision if expected_revision is None else expected_revision
        )
        if not isinstance(nodes, list) or not nodes:
            raise SceneError("Graph requires at least one node")
        if not isinstance(edges, list):
            raise SceneError("Graph edges must be a list")
        if len(nodes) > 200 or len(edges) > 500:
            raise SceneError("Graph is limited to 200 nodes and 500 edges")
        normalized_nodes = []
        for node in nodes:
            if not isinstance(node, dict):
                raise SceneError("Each graph node must be an object")
            if (
                not isinstance(node.get("id"), str)
                or not isinstance(node.get("label"), str)
                or not node["id"].strip()
                or not node["label"].strip()
                or len(node["id"]) > 200
                or len(node["label"]) > 2000
                or node.get("shape", "rectangle") not in SHAPES
            ):
                raise SceneError(
                    "Each graph node needs a unique ID, label and supported shape"
                )
            n_data = {**node, "shape": node.get("shape", "rectangle")}
            if "cluster" in node and node["cluster"] is not None:
                if not isinstance(node["cluster"], str) or not node["cluster"].strip():
                    raise SceneError(f"Node '{node['id']}' has invalid cluster ID")
                n_data["cluster"] = node["cluster"]
            normalized_nodes.append(n_data)

        node_ids = [node["id"] for node in normalized_nodes]
        if len(node_ids) != len(set(node_ids)):
            raise SceneError("Graph node IDs must be unique")
        allowed = set(node_ids)

        explicit_edge_ids = set()
        for edge in edges:
            if not isinstance(edge, dict):
                raise SceneError("Each graph edge must be an object")
            edge_id = edge.get("id")
            if edge_id is None:
                continue
            if (
                not isinstance(edge_id, str)
                or not edge_id.strip()
                or len(edge_id) > 200
                or edge_id in explicit_edge_ids
            ):
                raise SceneError("Graph edges need unique nonempty IDs")
            explicit_edge_ids.add(edge_id)

        edge_ids = set(explicit_edge_ids)
        normalized_edges = []
        generated_index = 1
        for edge in edges:
            edge_id = edge.get("id")
            if edge_id is None:
                while f"edge-{generated_index}" in edge_ids:
                    generated_index += 1
                edge_id = f"edge-{generated_index}"
                generated_index += 1
            if (
                edge.get("source") not in allowed
                or edge.get("target") not in allowed
                or not isinstance(edge.get("label", ""), str)
                or len(edge.get("label", "")) > 2000
            ):
                raise SceneError(
                    "Graph edges need unique IDs and existing source/target nodes"
                )
            if edge["source"] == edge["target"]:
                raise SceneError("Self-loop edges are not supported")
            edge_ids.add(edge_id)
            normalized_edges.append(
                {**edge, "id": edge_id, "label": edge.get("label", "")}
            )
        if direction not in ("horizontal", "vertical"):
            raise SceneError("direction must be horizontal or vertical")

        cluster_map = {}
        elements = []
        cluster_frames = []

        if clusters:
            if not isinstance(clusters, list):
                raise SceneError("clusters must be a list")
            c_ids = set()
            for c in clusters:
                cid = c.get("id") if isinstance(c, dict) else getattr(c, "id", None)
                if not cid or not isinstance(cid, str) or cid in c_ids:
                    raise SceneError("Cluster IDs must be unique non-empty strings")
                c_ids.add(cid)
            norm_clusters = [
                c if isinstance(c, dict) else c.model_dump() for c in clusters
            ]
            positioned, cluster_frames = clustered_layout(
                normalized_nodes,
                normalized_edges,
                norm_clusters,
                layout=layout,
                direction=direction,
            )
            for f in cluster_frames:
                frame_el = frame(
                    f["x"], f["y"], f["w"], f["h"], name=f["name"], **style
                )
                elements.append(frame_el)
                cluster_map[f["id"]] = frame_el["id"]
        else:
            if layout == "layered":
                try:
                    positioned = layered_layout(
                        normalized_nodes, normalized_edges, direction
                    )
                except SceneError as exc:
                    if cycle_fallback and "acyclic" in str(exc):
                        positioned = linear_layout(normalized_nodes, direction)
                    else:
                        raise
            elif layout in ("horizontal", "vertical"):
                positioned = linear_layout(normalized_nodes, layout)
            elif layout == "preset":
                positioned = normalized_nodes
            else:
                raise SceneError("layout must be layered, horizontal or vertical")

        id_map, positioned_map = (
            {},
            {node["id"]: node for node in positioned},
        )
        for node in positioned:
            f_id = cluster_map.get(node.get("frame_id"))
            node_style = dict(style)
            for k in (
                "strokeColor",
                "backgroundColor",
                "fillStyle",
                "strokeWidth",
                "strokeStyle",
                "opacity",
                "roughness",
                "roundness",
                "fontFamily",
                "font_family",
                "fontSize",
                "font_size",
            ):
                if node.get(k) is not None:
                    node_style[k] = node[k]
            group = _shape_elements(
                node["shape"],
                node["x"],
                node["y"],
                node["w"],
                node["h"],
                node["label"],
                node_style,
                frame_id=f_id,
            )
            elements.extend(group)
            id_map[node["id"]] = {
                "element_id": group[0]["id"],
                "label_id": group[1]["id"] if len(group) > 1 else None,
            }
        edge_map = {}
        canon_counts: dict[tuple[str, str], int] = {}
        for edge in normalized_edges:
            cp = tuple(sorted([edge["source"], edge["target"]]))
            canon_counts[cp] = canon_counts.get(cp, 0) + 1

        canon_seen: dict[tuple[str, str], int] = {}

        for edge in normalized_edges:
            source, target = (
                positioned_map[edge["source"]],
                positioned_map[edge["target"]],
            )
            start, end = boundary_point(source, target, 1), boundary_point(
                target, source, -1
            )
            cp = tuple(sorted([edge["source"], edge["target"]]))
            total_for_pair = canon_counts[cp]
            idx_for_pair = canon_seen.get(cp, 0)
            canon_seen[cp] = idx_for_pair + 1

            if total_for_pair > 1 and cp[0] != cp[1]:
                # Compute normal vector based on canonical pair node centers so opposing
                # edges share the same coordinate frame and are offset along parallel lanes
                n0 = positioned_map[cp[0]]
                n1 = positioned_map[cp[1]]
                c0_x = n0["x"] + n0["w"] / 2.0
                c0_y = n0["y"] + n0["h"] / 2.0
                c1_x = n1["x"] + n1["w"] / 2.0
                c1_y = n1["y"] + n1["h"] / 2.0
                dx = c1_x - c0_x
                dy = c1_y - c0_y
                dist = math.hypot(dx, dy)
                if dist > 1e-4:
                    nx = -dy / dist
                    ny = dx / dist
                    offset_mag = (idx_for_pair - (total_for_pair - 1) / 2.0) * 24.0
                    start = (start[0] + nx * offset_mag, start[1] + ny * offset_mag)
                    end = (end[0] + nx * offset_mag, end[1] + ny * offset_mag)

            edge_style = dict(style)
            for k in (
                "strokeColor",
                "strokeWidth",
                "strokeStyle",
                "opacity",
                "roughness",
                "fontFamily",
                "font_family",
                "fontSize",
                "font_size",
            ):
                if edge.get(k) is not None:
                    edge_style[k] = edge[k]
            edge_elbowed = edge.get("elbowed", elbowed)
            connector = arrow(*start, *end, elbowed=edge_elbowed, **edge_style)
            connector["startBinding"] = {
                "elementId": id_map[edge["source"]]["element_id"],
                "focus": 0,
                "gap": 0,
                "fixedPoint": [0.5, 0.5],
                "mode": "inside",
            }
            connector["endBinding"] = {
                "elementId": id_map[edge["target"]]["element_id"],
                "focus": 0,
                "gap": 0,
                "fixedPoint": [0.5, 0.5],
                "mode": "inside",
            }
            elements.append(connector)
            label_id = None
            if edge["label"]:
                edge_fs = edge_style.get("font_size", edge_style.get("fontSize", 14))
                edge_ff = edge_style.get(
                    "font_family", edge_style.get("fontFamily", style.get("font_family", 2))
                )
                label_el = text(
                    (start[0] + end[0]) / 2,
                    (start[1] + end[1]) / 2,
                    edge["label"],
                    fontSize=edge_fs,
                    fontFamily=edge_ff,
                    **edge_style,
                )
                bind_text(label_el, connector)
                _center_label(label_el, connector)
                elements.append(label_el)
                label_id = label_el["id"]
            edge_map[edge["id"]] = {
                "element_id": connector["id"],
                "label_id": label_id,
            }
        self.state.replace(new_document(elements), expected_revision=revision)
        result = {
            "status": "graph drawn",
            "nodes": len(nodes),
            "edges": len(edges),
            "node_map": id_map,
            "edge_map": edge_map,
            "revision": self.state.revision,
        }
        if clusters:
            result["cluster_map"] = cluster_map
        return result

    def set_element_locked(self, element_ids, locked: bool = True):
        """Unified method to lock or unlock elements and their bound labels."""
        if locked:
            return self.lock_elements(element_ids)
        return self.unlock_elements(element_ids)

    def lock_elements(self, element_ids):
        if not isinstance(element_ids, list) or not element_ids:
            raise SceneError("element_ids must be a non-empty list of element IDs")

        def apply_lock(document):
            index = _active(document)
            locked_ids = []
            for eid in element_ids:
                if not isinstance(eid, str) or not eid.strip():
                    raise SceneError("Element ID must be a non-empty string")
                el = _require(index, eid)
                el["locked"] = True
                locked_ids.append(eid)
                lbl = _label_for(index, eid)
                if lbl:
                    lbl["locked"] = True
                    locked_ids.append(lbl["id"])
            return {
                "status": "locked",
                "element_ids": locked_ids,
            }

        res = self.state.apply(apply_lock)
        return {**res, "revision": self.state.revision}

    def unlock_elements(self, element_ids):
        if not isinstance(element_ids, list) or not element_ids:
            raise SceneError("element_ids must be a non-empty list of element IDs")

        def apply_unlock(document):
            index = _active(document)
            unlocked_ids = []
            for eid in element_ids:
                if not isinstance(eid, str) or not eid.strip():
                    raise SceneError("Element ID must be a non-empty string")
                el = _require(index, eid)
                el["locked"] = False
                unlocked_ids.append(eid)
                lbl = _label_for(index, eid)
                if lbl:
                    lbl["locked"] = False
                    unlocked_ids.append(lbl["id"])
            return {
                "status": "unlocked",
                "element_ids": unlocked_ids,
            }

        res = self.state.apply(apply_unlock)
        return {**res, "revision": self.state.revision}

    def manage_groups(self, element_ids=None, group_id=None, action: str = "group"):
        """Unified method to group or ungroup diagram elements."""
        action_norm = (action or "group").strip().lower()
        if action_norm == "group":
            return self.group_elements(element_ids)
        elif action_norm == "ungroup":
            return self.ungroup_elements(element_ids=element_ids, group_id=group_id)
        raise SceneError(f"Invalid group action '{action}'; expected 'group' or 'ungroup'")

    def group_elements(self, element_ids):
        if not isinstance(element_ids, list) or len(element_ids) < 2:
            raise SceneError("Grouping requires a list of at least 2 element IDs")
        if len(set(element_ids)) != len(element_ids):
            raise SceneError("element_ids cannot contain duplicate IDs")

        def apply_group(document):
            import uuid

            index = _active(document)
            for eid in element_ids:
                if not isinstance(eid, str) or not eid.strip():
                    raise SceneError("Element ID must be a non-empty string")
                _require(index, eid)

            group_id = f"grp_{uuid.uuid4().hex[:12]}"
            for eid in element_ids:
                el = index[eid]
                groups = el.setdefault("groupIds", [])
                if group_id not in groups:
                    groups.append(group_id)
                lbl = _label_for(index, eid)
                if lbl:
                    lbl_groups = lbl.setdefault("groupIds", [])
                    if group_id not in lbl_groups:
                        lbl_groups.append(group_id)

            return {
                "status": "grouped",
                "group_id": group_id,
                "element_ids": element_ids,
            }

        res = self.state.apply(apply_group)
        return {**res, "revision": self.state.revision}

    def ungroup_elements(self, element_ids=None, group_id=None):
        if not element_ids and not group_id:
            raise SceneError("Provide either group_id or element_ids to ungroup")

        def apply_ungroup(document):
            index = _active(document)
            affected = set()
            removed_groups = set()

            if group_id:
                if not isinstance(group_id, str) or not group_id.strip():
                    raise SceneError("group_id must be a non-empty string")
                removed_groups.add(group_id)
                for el in index.values():
                    groups = el.get("groupIds", [])
                    if group_id in groups:
                        el["groupIds"] = [g for g in groups if g != group_id]
                        affected.add(el["id"])

            if element_ids:
                if not isinstance(element_ids, list) or not element_ids:
                    raise SceneError("element_ids must be a non-empty list of IDs")
                for eid in element_ids:
                    el = _require(index, eid)
                    groups = el.get("groupIds", [])
                    if groups:
                        popped = groups.pop()
                        removed_groups.add(popped)
                        affected.add(eid)
                        lbl = _label_for(index, eid)
                        if lbl:
                            lbl_groups = lbl.get("groupIds", [])
                            if popped in lbl_groups:
                                lbl["groupIds"] = [
                                    g for g in lbl_groups if g != popped
                                ]
                                affected.add(lbl["id"])

            return {
                "status": "ungrouped",
                "affected_elements": sorted(affected),
                "removed_group_ids": sorted(removed_groups),
            }

        res = self.state.apply(apply_ungroup)
        return {**res, "revision": self.state.revision}

    def draw_mermaid(
        self,
        mermaid_code: str,
        direction: str | None = None,
        layout: str = "layered",
        elbowed: bool = False,
        roundness: str | None = None,
    ):
        from .mermaid import parse_mermaid

        nodes, edges, clusters, parsed_direction, parsed_layout = parse_mermaid(
            mermaid_code=mermaid_code,
            direction=direction,
            layout=layout,
        )
        return self.draw_graph(
            nodes=[node.model_dump() for node in nodes],
            edges=[edge.model_dump() for edge in edges],
            clusters=[cluster.model_dump() for cluster in clusters]
            if clusters
            else None,
            layout=parsed_layout,
            direction=parsed_direction,
            elbowed=elbowed,
            roundness=roundness,
            cycle_fallback=True,
        )

    def get_viewport(self):
        doc, revision = self.state.snapshot()
        app_state = doc.get("appState") or {}
        zoom_obj = app_state.get("zoom")
        zoom_val = (
            zoom_obj.get("value", 1.0)
            if isinstance(zoom_obj, dict)
            else 1.0
        )
        scroll_x = float(app_state.get("scrollX", 0.0))
        scroll_y = float(app_state.get("scrollY", 0.0))
        bg = str(app_state.get("viewBackgroundColor", "#ffffff"))
        return {
            "scroll_x": scroll_x,
            "scroll_y": scroll_y,
            "zoom": zoom_val,
            "view_background_color": bg,
            "revision": revision,
        }

    def set_viewport(
        self,
        scroll_x=None,
        scroll_y=None,
        zoom=None,
        background_color=None,
        focus_element_ids=None,
        padding=50.0,
    ):
        if focus_element_ids is not None:
            res = self.focus_elements(focus_element_ids, padding=padding)
            if (
                scroll_x is None
                and scroll_y is None
                and zoom is None
                and background_color is None
            ):
                return res

        if scroll_x is not None and not _finite_number(scroll_x):
            raise SceneError("scroll_x must be a finite number")
        if scroll_y is not None and not _finite_number(scroll_y):
            raise SceneError("scroll_y must be a finite number")
        if zoom is not None:
            if not _finite_number(zoom) or zoom <= 0 or zoom > 50.0:
                raise SceneError(
                    "zoom must be a positive number between 0.01 and 50.0"
                )
        if background_color is not None:
            import re
            from .validation import COLOR_PATTERN

            if not re.match(f"^{COLOR_PATTERN}$", background_color):
                raise SceneError(
                    f"Invalid hex color format: {background_color}"
                )

        def apply_viewport(document):
            app_state = document.setdefault("appState", {})
            if scroll_x is not None:
                app_state["scrollX"] = float(scroll_x)
            if scroll_y is not None:
                app_state["scrollY"] = float(scroll_y)
            if zoom is not None:
                app_state["zoom"] = {"value": float(zoom)}
            if background_color is not None:
                app_state["viewBackgroundColor"] = background_color

            zoom_val = (
                app_state.get("zoom", {}).get("value", 1.0)
                if isinstance(app_state.get("zoom"), dict)
                else 1.0
            )
            return {
                "scroll_x": float(app_state.get("scrollX", 0.0)),
                "scroll_y": float(app_state.get("scrollY", 0.0)),
                "zoom": zoom_val,
                "view_background_color": str(
                    app_state.get("viewBackgroundColor", "#ffffff")
                ),
            }

        res = self.state.apply(apply_viewport, remember=False)
        return {**res, "revision": self.state.revision}

    def focus_elements(
        self,
        element_ids=None,
        padding=50.0,
        viewport_width=1920.0,
        viewport_height=1080.0,
    ):
        if not _finite_number(padding) or padding < 0:
            raise SceneError("padding must be a non-negative number")
        if not _finite_number(viewport_width) or viewport_width <= 0:
            raise SceneError("viewport_width must be a positive number")
        if not _finite_number(viewport_height) or viewport_height <= 0:
            raise SceneError("viewport_height must be a positive number")

        def apply_focus(document):
            index = _active(document)
            if element_ids is not None:
                if not isinstance(element_ids, list) or not element_ids:
                    raise SceneError(
                        "element_ids must be a non-empty list of IDs"
                    )
                targets = []
                for eid in element_ids:
                    targets.append(_require(index, eid))
            else:
                targets = [
                    el
                    for el in document["elements"]
                    if not el.get("isDeleted")
                ]

            if not targets:
                app_state = document.setdefault("appState", {})
                app_state["scrollX"] = 0.0
                app_state["scrollY"] = 0.0
                app_state["zoom"] = {"value": 1.0}
                return {
                    "status": "focused",
                    "scroll_x": 0.0,
                    "scroll_y": 0.0,
                    "zoom": 1.0,
                    "bounding_box": {
                        "x": 0.0,
                        "y": 0.0,
                        "width": 0.0,
                        "height": 0.0,
                    },
                    "focused_element_ids": [],
                }

            min_x = min(_element_bounds(el)[0] for el in targets)
            min_y = min(_element_bounds(el)[1] for el in targets)
            max_x = max(_element_bounds(el)[2] for el in targets)
            max_y = max(_element_bounds(el)[3] for el in targets)
            bb_w = max(1.0, max_x - min_x)
            bb_h = max(1.0, max_y - min_y)

            avail_w = max(50.0, viewport_width - 2 * padding)
            avail_h = max(50.0, viewport_height - 2 * padding)
            fit_zoom = min(2.0, max(0.05, min(avail_w / bb_w, avail_h / bb_h)))

            center_x = min_x + bb_w / 2
            center_y = min_y + bb_h / 2
            scroll_x = (viewport_width / 2) - center_x * fit_zoom
            scroll_y = (viewport_height / 2) - center_y * fit_zoom

            app_state = document.setdefault("appState", {})
            app_state["scrollX"] = scroll_x
            app_state["scrollY"] = scroll_y
            app_state["zoom"] = {"value": fit_zoom}

            return {
                "status": "focused",
                "scroll_x": scroll_x,
                "scroll_y": scroll_y,
                "zoom": fit_zoom,
                "bounding_box": {
                    "x": min_x,
                    "y": min_y,
                    "width": bb_w,
                    "height": bb_h,
                },
                "focused_element_ids": [el["id"] for el in targets],
            }

        res = self.state.apply(apply_focus, remember=False)
        return {**res, "revision": self.state.revision}

    def get_scene_summary(self):
        doc, revision = self.state.snapshot()
        index = _active(doc)
        elements = [el for el in doc["elements"] if not el.get("isDeleted")]

        type_counts = {}
        for el in elements:
            t = el.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        frames = []
        groups_map = {}
        connectors = []
        code_blocks = []
        connected_shape_ids = set()

        for el in elements:
            for gid in el.get("groupIds", []):
                groups_map.setdefault(gid, []).append(el["id"])

            if el["type"] == "frame":
                children = [
                    c["id"] for c in elements if c.get("frameId") == el["id"]
                ]
                frames.append(
                    {
                        "id": el["id"],
                        "name": el.get("name", ""),
                        "x": el["x"],
                        "y": el["y"],
                        "width": el["width"],
                        "height": el["height"],
                        "children_count": len(children),
                        "children_ids": children,
                    }
                )

            elif el["type"] == "arrow":
                src = (el.get("startBinding") or {}).get("elementId")
                tgt = (el.get("endBinding") or {}).get("elementId")
                if src:
                    connected_shape_ids.add(src)
                if tgt:
                    connected_shape_ids.add(tgt)
                lbl = _label_for(index, el["id"])
                connectors.append(
                    {
                        "id": el["id"],
                        "source": src,
                        "target": tgt,
                        "label": lbl.get("text") if lbl else None,
                        "elbowed": el.get("elbowed", False),
                    }
                )

            custom_data = el.get("customData") or {}
            if custom_data.get("type") in ("code_block", "code-block"):
                code_text = custom_data.get("code", "")
                code_blocks.append(
                    {
                        "container_id": el["id"],
                        "language": custom_data.get("language", "text"),
                        "title": custom_data.get("title"),
                        "lines_count": len(code_text.splitlines()) if code_text else custom_data.get("lines_count", 0),
                    }
                )

        groups = [
            {"group_id": gid, "element_ids": ids}
            for gid, ids in groups_map.items()
        ]

        standalone_elements = []
        for el in elements:
            if el["type"] not in ("arrow", "frame") and not el.get(
                "containerId"
            ):
                if (
                    el["id"] not in connected_shape_ids
                    and not el.get("frameId")
                    and not el.get("groupIds")
                ):
                    standalone_elements.append(el["id"])

        bounds = None
        if elements:
            min_x = min(_element_bounds(el)[0] for el in elements)
            min_y = min(_element_bounds(el)[1] for el in elements)
            max_x = max(_element_bounds(el)[2] for el in elements)
            max_y = max(_element_bounds(el)[3] for el in elements)
            bounds = {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            }

        desc_parts = [
            f"Scene (revision {revision}) contains {len(elements)} active elements: "
            + ", ".join(f"{cnt} {t}" for t, cnt in sorted(type_counts.items()))
            + "."
        ]
        if frames:
            desc_parts.append(
                f"Contains {len(frames)} frame container(s): "
                + ", ".join(
                    f"'{f['name'] or f['id']}' ({f['children_count']} children)"
                    for f in frames
                )
                + "."
            )
        if connectors:
            desc_parts.append(
                f"Defines {len(connectors)} connector flow(s) linking {len(connected_shape_ids)} node(s)."
            )
        if code_blocks:
            desc_parts.append(
                f"Includes {len(code_blocks)} code block(s) ({', '.join(cb['language'] for cb in code_blocks)})."
            )
        if groups:
            desc_parts.append(
                f"Organized into {len(groups)} multi-element group(s)."
            )
        if bounds:
            desc_parts.append(
                f"Canvas bounds span from ({bounds['min_x']:.0f}, {bounds['min_y']:.0f}) to ({bounds['max_x']:.0f}, {bounds['max_y']:.0f}) [dimensions: {bounds['width']:.0f}x{bounds['height']:.0f}]."
            )

        return {
            "element_count": len(elements),
            "type_counts": type_counts,
            "frames": frames,
            "groups": groups,
            "connectors": connectors,
            "code_blocks": code_blocks,
            "standalone_elements": standalone_elements,
            "bounds": bounds,
            "description": " ".join(desc_parts),
            "revision": revision,
        }

    def duplicate_elements(self, element_ids, offset_x=20.0, offset_y=20.0):
        if not isinstance(element_ids, list) or not element_ids:
            raise SceneError("element_ids must be a non-empty list of element IDs")
        if not _finite_number(offset_x) or not _finite_number(offset_y):
            raise SceneError("offset_x and offset_y must be finite numbers")

        def apply_duplicate(document):
            import random
            import uuid
            from copy import deepcopy

            index = _active(document)
            for eid in element_ids:
                if not isinstance(eid, str) or not eid.strip():
                    raise SceneError("Element ID must be a non-empty string")
                _require(index, eid)

            targets_set = list(element_ids)
            for eid in element_ids:
                lbl = _label_for(index, eid)
                if lbl and lbl["id"] not in targets_set:
                    targets_set.append(lbl["id"])

            id_map = {
                old_id: f"{index[old_id]['type']}_{uuid.uuid4().hex[:10]}"
                for old_id in targets_set
            }

            group_map = {}
            for old_id in targets_set:
                for gid in index[old_id].get("groupIds", []):
                    if gid not in group_map:
                        group_map[gid] = f"grp_{uuid.uuid4().hex[:12]}"

            duplicated_elements = []
            for old_id in targets_set:
                orig = index[old_id]
                cloned = deepcopy(orig)
                cloned["id"] = id_map[old_id]
                cloned["x"] += offset_x
                cloned["y"] += offset_y
                cloned["seed"] = random.randrange(1, 2**31)
                cloned["versionNonce"] = random.randrange(1, 2**31)
                cloned["version"] = 1
                cloned["locked"] = False

                if cloned.get("containerId") and cloned["containerId"] in id_map:
                    cloned["containerId"] = id_map[cloned["containerId"]]
                elif cloned.get("containerId"):
                    cloned["containerId"] = None

                if cloned.get("frameId") and cloned["frameId"] in id_map:
                    cloned["frameId"] = id_map[cloned["frameId"]]
                elif cloned.get("frameId"):
                    if cloned["frameId"] not in index:
                        cloned["frameId"] = None

                if cloned.get("boundElements"):
                    cloned["boundElements"] = [
                        {**b, "id": id_map[b["id"]]}
                        for b in cloned["boundElements"]
                        if b["id"] in id_map
                    ]

                if cloned.get("groupIds"):
                    cloned["groupIds"] = [
                        group_map[gid]
                        for gid in cloned["groupIds"]
                        if gid in group_map
                    ]

                if cloned.get("type") == "arrow":
                    for end in ("startBinding", "endBinding"):
                        binding = cloned.get(end)
                        if binding:
                            src_id = binding.get("elementId")
                            if src_id in id_map:
                                binding["elementId"] = id_map[src_id]
                            else:
                                cloned[end] = None

                duplicated_elements.append(cloned)

            document["elements"].extend(duplicated_elements)
            return {
                "status": "duplicated",
                "original_ids": element_ids,
                "duplicated_ids": [id_map[eid] for eid in element_ids],
                "id_mapping": id_map,
            }

        res = self.state.apply(apply_duplicate)
        return {**res, "revision": self.state.revision}

    def describe_scene(self, detailed=True):
        doc, revision = self.state.snapshot()
        index = _active(doc)
        elements = [el for el in doc.get("elements", []) if not el.get("isDeleted")]

        lines = [f"=== Scene Description (Revision {revision}) ==="]
        lines.append(f"Total Elements: {len(elements)}")

        bounds = None
        if elements:
            min_x = min(_element_bounds(el)[0] for el in elements)
            min_y = min(_element_bounds(el)[1] for el in elements)
            max_x = max(_element_bounds(el)[2] for el in elements)
            max_y = max(_element_bounds(el)[3] for el in elements)
            bounds = {
                "min_x": min_x,
                "min_y": min_y,
                "max_x": max_x,
                "max_y": max_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
            }
            lines.append(
                f"Canvas Bounds: ({min_x:.0f}, {min_y:.0f}) to ({max_x:.0f}, {max_y:.0f}) [Size: {bounds['width']:.0f}x{bounds['height']:.0f}]"
            )

        element_summaries = []
        for el in elements:
            lbl = _label_for(index, el["id"])
            lbl_text = (
                lbl.get("text")
                if lbl
                else (
                    el.get("name")
                    if el["type"] == "frame"
                    else (el.get("text") if el["type"] == "text" else None)
                )
            )
            info = {
                "id": el["id"],
                "type": el["type"],
                "position": {"x": el["x"], "y": el["y"]},
                "dimensions": {
                    "width": el.get("width", 0),
                    "height": el.get("height", 0),
                },
                "label": lbl_text,
                "stroke_color": el.get("strokeColor"),
                "background_color": el.get("backgroundColor"),
                "frame_id": el.get("frameId"),
                "group_ids": el.get("groupIds", []),
                "locked": el.get("locked", False),
            }
            element_summaries.append(info)

        connections = []
        for el in elements:
            if el["type"] == "arrow":
                src = (el.get("startBinding") or {}).get("elementId")
                tgt = (el.get("endBinding") or {}).get("elementId")
                src_lbl = (
                    _label_for(index, src).get("text")
                    if src and _label_for(index, src)
                    else (index.get(src, {}).get("text") if src in index else src)
                )
                tgt_lbl = (
                    _label_for(index, tgt).get("text")
                    if tgt and _label_for(index, tgt)
                    else (index.get(tgt, {}).get("text") if tgt in index else tgt)
                )
                lbl = _label_for(index, el["id"])
                edge_info = {
                    "arrow_id": el["id"],
                    "source_id": src,
                    "target_id": tgt,
                    "source_label": src_lbl,
                    "target_label": tgt_lbl,
                    "label": lbl.get("text") if lbl else None,
                    "elbowed": el.get("elbowed", False),
                }
                connections.append(edge_info)

        if len(connections) > 1:
            layout_type = "connected_graph"
        elif any(el["type"] == "frame" for el in elements):
            layout_type = "clustered_frames"
        else:
            layout_type = "freeform"

        lines.append(f"Layout Pattern: {layout_type}")

        if connections:
            lines.append("\nFlow Connections:")
            for c in connections:
                src_desc = (
                    f"'{c['source_label']}' ({c['source_id']})"
                    if c["source_label"]
                    else (c["source_id"] or "unbound")
                )
                tgt_desc = (
                    f"'{c['target_label']}' ({c['target_id']})"
                    if c["target_label"]
                    else (c["target_id"] or "unbound")
                )
                lbl_desc = f" via '{c['label']}'" if c["label"] else ""
                elbow_desc = " [elbowed]" if c["elbowed"] else ""
                lines.append(f"  - {src_desc} --> {tgt_desc}{lbl_desc}{elbow_desc}")

        if detailed:
            lines.append("\nElements Detail:")
            for es in element_summaries:
                lbl_part = f" label='{es['label']}'" if es["label"] else ""
                frame_part = f" inside frame='{es['frame_id']}'" if es["frame_id"] else ""
                lock_part = " [LOCKED]" if es["locked"] else ""
                lines.append(
                    f"  - [{es['type']}] id='{es['id']}' at ({es['position']['x']:.0f}, {es['position']['y']:.0f}) size={es['dimensions']['width']:.0f}x{es['dimensions']['height']:.0f}{lbl_part}{frame_part}{lock_part}"
                )

        return {
            "summary": "\n".join(lines),
            "element_count": len(elements),
            "layout_type": layout_type,
            "elements": element_summaries,
            "connections": connections,
            "bounds": bounds,
            "revision": revision,
        }

    def export_to_excalidraw_url(self, name=None, timeout=12.0, verify=True):
        if name:
            doc = load_scene(name)
        else:
            doc = self.state.document()
        from .sharing import export_to_excalidraw_url

        res = export_to_excalidraw_url(doc, timeout=timeout, verify=verify)
        return {**res, "revision": self.state.revision}

    def import_scene(self, data, mode="replace", offset_x=0.0, offset_y=0.0):
        from .importer import import_scene

        return import_scene(
            service=self,
            data=data,
            mode=mode,
            offset_x=offset_x,
            offset_y=offset_y,
        )

    def get_resource(self, uri=None, resource_type=None, identifier=None):
        from .resources import get_resource

        return get_resource(
            service=self,
            uri=uri,
            resource_type=resource_type,
            identifier=identifier,
        )

    def read_diagram_guide(self, topic=None):
        from .design_guide import get_diagram_guide

        return get_diagram_guide(topic=topic)

    def start_live_server(self, host="127.0.0.1", port=8080):
        from .live_server import LiveCanvasServer

        if self._live_server is None:
            self._live_server = LiveCanvasServer(service=self, host=host, port=port)
        try:
            return self._live_server.start(host=host, port=port)
        except Exception:
            self._live_server = None
            raise

    def stop_live_server(self):
        if self._live_server is not None:
            res = self._live_server.stop()
            self._live_server = None
            return res
        return {"status": "not_running"}

    def get_live_server_status(self):
        if self._live_server is not None:
            return self._live_server.get_status()
        return {
            "is_running": False,
            "url": None,
            "host": "127.0.0.1",
            "port": 8080,
            "active_clients": 0,
        }

