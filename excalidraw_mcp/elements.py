import uuid
import random
import time


# Explicit project defaults; never depend on the editor's current UI defaults.
DEFAULT_STYLE = {
    "strokeColor": "#1e1e1e",
    "backgroundColor": "transparent",
    "fillStyle": "solid",
    "strokeWidth": 2,
    "strokeStyle": "solid",
    "roughness": 1,
    "opacity": 100,
    "angle": 0,
}


def _apply_style(el: dict, style_kwargs: dict):
    """Merge style keyword arguments into an element dict, using defaults where not specified."""
    for key in DEFAULT_STYLE:
        if key in style_kwargs and style_kwargs[key] is not None:
            el[key] = style_kwargs[key]
        else:
            el[key] = DEFAULT_STYLE[key]
    # seed is required by Excalidraw for rendering
    el["seed"] = random.randint(1, 1000000)
    el["version"] = 1
    el["versionNonce"] = random.randrange(1, 2**31)
    el["updated"] = time.time_ns() // 1_000_000

    roundness_val = None
    if "roundness" in style_kwargs and style_kwargs["roundness"] is not None:
        r = style_kwargs["roundness"]
        if r == "adaptive":
            roundness_val = {"type": 3}
        elif r == "round":
            roundness_val = {"type": 2}
        elif r == "sharp":
            roundness_val = None
        elif isinstance(r, dict):
            roundness_val = r

    frame_id = style_kwargs.get("frameId") or style_kwargs.get("frame_id")

    el.update(
        index=None,
        groupIds=[],
        frameId=frame_id,
        boundElements=[],
        link=None,
        locked=False,
        isDeleted=False,
        roundness=roundness_val,
    )


def _base_shape(shape_type: str, x: int, y: int, w: int, h: int, **style):
    el = {
        "id": str(uuid.uuid4()),
        "type": shape_type,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
    }
    _apply_style(el, style)
    return el


def rect(x: int, y: int, w: int, h: int, **style):
    return _base_shape("rectangle", x, y, w, h, **style)


def ellipse(x: int, y: int, w: int, h: int, **style):
    return _base_shape("ellipse", x, y, w, h, **style)


def diamond(x: int, y: int, w: int, h: int, **style):
    return _base_shape("diamond", x, y, w, h, **style)


def frame(x: int, y: int, w: int, h: int, name: str = "", **style):
    el = {
        "id": str(uuid.uuid4()),
        "type": "frame",
        "name": name,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
    }
    _apply_style(el, style)
    return el


def normalize_font_family(family: int | str | None) -> int:
    """Normalize font family name or number to Excalidraw integer code.

    1: Excalifont / Virgil (Hand-drawn)
    2: Sans-serif / Helvetica (Normal)
    3: Cascadia / Monospace (Code)
    4: Comic Shanns
    """
    if family is None:
        return 2
    if isinstance(family, int):
        return family if family >= 1 else 2
    f_str = str(family).strip().lower()
    if f_str in ("1", "excalifont", "virgil", "handwriting", "hand-drawn", "hand"):
        return 1
    if f_str in ("2", "sans-serif", "sans", "helvetica", "normal"):
        return 2
    if f_str in ("3", "monospace", "mono", "code", "cascadia"):
        return 3
    if f_str in ("4", "comic-shanns", "comic", "comic shanns"):
        return 4
    if f_str.isdigit() and int(f_str) >= 1:
        return int(f_str)
    return 2


def text(
    x: float | int,
    y: float | int,
    content: str,
    fontSize: int = 20,
    fontFamily: int | str = 2,
    **style,
):
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    ff = style.pop("font_family", style.pop("fontFamily", fontFamily))
    fs = style.pop("font_size", style.pop("fontSize", fontSize))
    norm_ff = normalize_font_family(ff)
    custom_data = style.pop("customData", {}) or {}
    if isinstance(ff, str) and ff.strip().lower() not in (
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
        custom_data["fontFamily"] = ff.strip()

    lines = content.split("\n")
    text_w = max(map(len, lines)) * fs * 0.6 if lines else 20.0
    text_h = len(lines) * fs * 1.25 if lines else float(fs) * 1.25

    el = {
        "id": str(uuid.uuid4()),
        "type": "text",
        "x": x,
        "y": y,
        "text": content,
        "fontSize": fs,
        "width": text_w,
        "height": text_h,
        "fontFamily": norm_ff,
        "lineHeight": 1.25,
        "textAlign": "left",
        "verticalAlign": "top",
        "originalText": content,
        "autoResize": True,
        "containerId": None,
    }
    if custom_data:
        el["customData"] = custom_data
    _apply_style(el, style)
    return el


def arrow(x, y, x2, y2, elbowed=False, **style):
    is_elbowed = bool(style.pop("elbowed", elbowed))
    el = {
        "id": str(uuid.uuid4()),
        "type": "arrow",
        "x": x,
        "y": y,
        "points": [[0, 0], [x2 - x, y2 - y]],
        "width": abs(x2 - x),
        "height": abs(y2 - y),
        "startBinding": None,
        "endBinding": None,
        "startArrowhead": None,
        "endArrowhead": "arrow",
        "lastCommittedPoint": None,
        "elbowed": is_elbowed,
    }
    _apply_style(el, style)
    return el


def bind_text(text_el: dict, container_el: dict):
    """Bind a text element as the label of a container shape."""
    text_el["containerId"] = container_el["id"]
    is_code_block = (container_el.get("customData") or {}).get("type") in ("code_block", "code-block")
    if not is_code_block:
        text_el["textAlign"] = "center"
        text_el["verticalAlign"] = "middle"
    else:
        text_el.setdefault("textAlign", "left")
        text_el.setdefault("verticalAlign", "top")
    text_el["angle"] = container_el.get("angle", 0)

    text_id = text_el["id"]
    if container_el.get("boundElements") is None:
        container_el["boundElements"] = []

    # Avoid duplicates if bind_text is called multiple times
    if not any(b["id"] == text_id for b in container_el["boundElements"]):
        container_el["boundElements"].append({"type": "text", "id": text_id})
