"""Image preview and export renderer for Excalidraw scenes.

Renders canvas elements into PNG image bytes suitable for inline display
in MCP clients and direct file exports. Features:
- Comprehensive system font discovery & fallback
- High-fidelity syntax-highlighted code blocks with themes
- Clustered frames, decision diamonds, ellipses, and adaptive rounded rectangles
- Multi-point and elbowed connectors with accurate arrowheads
"""

import io
import json
import math
from typing import Any

from PIL import Image, ImageDraw, ImageFont, PngImagePlugin

from excalidraw_mcp.code_blocks import get_theme, highlight_code
from excalidraw_mcp.fonts import get_font


def _parse_color(
    color_str: str | None, opacity: int | float = 100
) -> tuple[int, int, int, int]:
    """Parse Excalidraw color string into an RGBA 4-tuple."""
    if not color_str or color_str.strip().lower() == "transparent":
        return (0, 0, 0, 0)

    color_str = color_str.strip()
    alpha_mul = max(0.0, min(1.0, float(opacity) / 100.0))

    if color_str.startswith("#"):
        hex_val = color_str.lstrip("#")
        if len(hex_val) == 3:
            r = int(hex_val[0] * 2, 16)
            g = int(hex_val[1] * 2, 16)
            b = int(hex_val[2] * 2, 16)
            return (r, g, b, int(255 * alpha_mul))
        if len(hex_val) == 4:
            r = int(hex_val[0] * 2, 16)
            g = int(hex_val[1] * 2, 16)
            b = int(hex_val[2] * 2, 16)
            a = int(hex_val[3] * 2, 16)
            return (r, g, b, int(a * alpha_mul))
        if len(hex_val) == 6:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return (r, g, b, int(255 * alpha_mul))
        if len(hex_val) == 8:
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            orig_a = int(hex_val[6:8], 16)
            return (r, g, b, int(orig_a * alpha_mul))

    # Named fallback
    low = color_str.lower()
    if low in ("white", "#fff", "#ffffff"):
        return (255, 255, 255, int(255 * alpha_mul))
    if low in ("black", "#000", "#000000"):
        return (0, 0, 0, int(255 * alpha_mul))
    return (30, 30, 30, int(255 * alpha_mul))


def _compute_bounds(
    elements: list[dict[str, Any]],
    default_box: tuple[float, float, float, float] = (0.0, 0.0, 600.0, 400.0),
) -> tuple[float, float, float, float]:
    """Compute the world-coordinate bounding box of active elements."""
    if not elements:
        return default_box

    min_x = float("inf")
    min_y = float("inf")
    max_x = float("-inf")
    max_y = float("-inf")

    for el in elements:
        x, y = float(el.get("x", 0)), float(el.get("y", 0))
        w, h = float(el.get("width", 0)), float(el.get("height", 0))
        etype = el.get("type")
        angle = float(el.get("angle", 0))

        if etype in ("arrow", "line", "freedraw"):
            points = el.get("points") or [[0.0, 0.0], [w, h]]
            if abs(angle) > 1e-4:
                cx = x + w / 2.0
                cy = y + h / 2.0
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                for pt in points:
                    px = x + float(pt[0])
                    py = y + float(pt[1])
                    rx = cx + (px - cx) * cos_a - (py - cy) * sin_a
                    ry = cy + (px - cx) * sin_a + (py - cy) * cos_a
                    min_x = min(min_x, rx)
                    min_y = min(min_y, ry)
                    max_x = max(max_x, rx)
                    max_y = max(max_y, ry)
            else:
                for pt in points:
                    px = x + float(pt[0])
                    py = y + float(pt[1])
                    min_x = min(min_x, px)
                    min_y = min(min_y, py)
                    max_x = max(max_x, px)
                    max_y = max(max_y, py)
        else:
            if abs(angle) > 1e-4:
                cx = x + w / 2.0
                cy = y + h / 2.0
                cos_a = math.cos(angle)
                sin_a = math.sin(angle)
                hw, hh = w / 2.0, h / 2.0
                for dx, dy in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)):
                    rx = cx + dx * cos_a - dy * sin_a
                    ry = cy + dx * sin_a + dy * cos_a
                    min_x = min(min_x, rx)
                    min_y = min(min_y, ry)
                    max_x = max(max_x, rx)
                    max_y = max(max_y, ry)
            else:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x + w)
                max_y = max(max_y, y + h)

    if min_x == float("inf"):
        return default_box

    if max_x - min_x < 20:
        max_x = min_x + 100
    if max_y - min_y < 20:
        max_y = min_y + 100

    return min_x, min_y, max_x, max_y


def _draw_dashed_line(
    draw: ImageDraw.ImageDraw,
    p1: tuple[float, float],
    p2: tuple[float, float],
    fill: tuple[int, int, int, int],
    width: int = 1,
    dash_len: float = 8.0,
    gap_len: float = 5.0,
):
    """Draw a 2D line segment with dashes."""
    x1, y1 = p1
    x2, y2 = p2
    dx = x2 - x1
    dy = y2 - y1
    dist = math.hypot(dx, dy)
    if dist < 1e-4:
        return

    ux = dx / dist
    uy = dy / dist
    cur = 0.0

    while cur < dist:
        seg_end = min(cur + dash_len, dist)
        sp = (x1 + cur * ux, y1 + cur * uy)
        ep = (x1 + seg_end * ux, y1 + seg_end * uy)
        draw.line([sp, ep], fill=fill, width=width)
        cur += dash_len + gap_len


def _draw_polyline(
    draw: ImageDraw.ImageDraw,
    pts: list[tuple[float, float]],
    fill: tuple[int, int, int, int],
    width: int = 1,
    stroke_style: str = "solid",
):
    """Draw a polyline supporting solid, dashed, and dotted styles."""
    if len(pts) < 2:
        return
    if stroke_style not in ("dashed", "dotted"):
        draw.line(pts, fill=fill, width=width)
        return

    dash_len, gap_len = (8.0, 5.0) if stroke_style == "dashed" else (3.0, 3.0)
    for i in range(len(pts) - 1):
        _draw_dashed_line(
            draw,
            pts[i],
            pts[i + 1],
            fill=fill,
            width=width,
            dash_len=dash_len,
            gap_len=gap_len,
        )


def _draw_arrowhead(
    draw: ImageDraw.ImageDraw,
    tip: tuple[float, float],
    prev_pt: tuple[float, float],
    fill: tuple[int, int, int, int],
    size: float = 14.0,
    angle_deg: float = 26.0,
):
    """Draw a classic filled arrowhead pointing at tip."""
    tx, ty = tip
    px, py = prev_pt
    dx = tx - px
    dy = ty - py
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return

    ux = dx / length
    uy = dy / length

    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    lx = tx - size * (ux * cos_a - uy * sin_a)
    ly = ty - size * (uy * cos_a + ux * sin_a)
    rx = tx - size * (ux * cos_a + uy * sin_a)
    ry = ty - size * (uy * cos_a - ux * sin_a)

    draw.polygon([(tx, ty), (lx, ly), (rx, ry)], fill=fill)


def render_scene_image(
    document: dict[str, Any],
    scale: float = 1.0,
    padding: int = 40,
    background: bool = True,
) -> tuple[bytes, int, int]:
    """Render an Excalidraw document dictionary to PNG image bytes and dimensions.

    Returns:
        (png_bytes, width, height)
    """
    scale = max(0.25, min(4.0, float(scale)))
    padding = max(0, min(200, int(padding)))

    elements = [
        el for el in document.get("elements", []) if not el.get("isDeleted")
    ]
    app_state = document.get("appState") or {}
    bg_color_hex = app_state.get("viewBackgroundColor", "#ffffff")

    canvas_bg = _parse_color(bg_color_hex, 100)
    if canvas_bg[3] == 0:
        canvas_bg = (255, 255, 255, 255)

    if background:
        bg_color = canvas_bg
    else:
        bg_color = (0, 0, 0, 0)

    min_x, min_y, max_x, max_y = _compute_bounds(elements)

    # Adaptive outer margin for large architectures when default padding is used
    if padding == 40 and (max_x - min_x > 1500 or max_y - min_y > 1500):
        padding = max(40, min(140, int(0.03 * max(max_x - min_x, max_y - min_y))))

    world_w = max_x - min_x + 2 * padding
    world_h = max_y - min_y + 2 * padding

    # Clamping scale so maximum dimensions don't exceed max_canvas_dim while preserving readability
    max_canvas_dim = 8192.0 if scale > 1.0 else 4096.0
    effective_scale = min(
        scale,
        max_canvas_dim / max(1.0, world_w),
        max_canvas_dim / max(1.0, world_h),
    )

    target_w = world_w * effective_scale
    target_h = world_h * effective_scale

    img_w = max(100, min(int(max_canvas_dim), int(round(target_w))))
    img_h = max(100, min(int(max_canvas_dim), int(round(target_h))))

    offset_x = (img_w - target_w) / 2.0
    offset_y = (img_h - target_h) / 2.0

    image = Image.new("RGBA", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(image)

    def tx(wx: float) -> float:
        return offset_x + (wx - min_x + padding) * effective_scale

    def ty(wy: float) -> float:
        return offset_y + (wy - min_y + padding) * effective_scale

    if not elements:
        font = get_font("sans-serif", int(18 * effective_scale))
        draw.text(
            (img_w / 2, img_h / 2),
            "(Empty Excalidraw Canvas)",
            fill=(160, 160, 160, 255),
            font=font,
            anchor="mm",
        )
        buf = io.BytesIO()
        info = PngImagePlugin.PngInfo()
        try:
            info.add_text("application/vnd.excalidraw+json", json.dumps(document, ensure_ascii=False))
        except Exception:
            pass
        image.save(buf, format="PNG", pnginfo=info)
        return buf.getvalue(), img_w, img_h

    # Identify bound text elements of code blocks so they are not rendered twice
    code_block_text_ids = set()
    for el in elements:
        if (el.get("customData") or {}).get("type") in ("code_block", "code-block"):
            for b in el.get("boundElements", []):
                if b.get("type") == "text":
                    code_block_text_ids.add(b["id"])

    # Categorize elements for layered rendering
    frames = []
    shapes = []
    arrows = []
    texts = []
    element_index = {el["id"]: el for el in elements if el.get("id")}

    for el in elements:
        etype = el.get("type")
        if etype == "frame":
            frames.append(el)
        elif etype in ("rectangle", "diamond", "ellipse"):
            shapes.append(el)
        elif etype in ("arrow", "line", "freedraw"):
            arrows.append(el)
        elif etype == "text":
            if el.get("id") not in code_block_text_ids:
                texts.append(el)

    # 1. Render Frames
    for f in frames:
        fx = tx(f.get("x", 0))
        fy = ty(f.get("y", 0))
        fw = f.get("width", 0) * effective_scale
        fh = f.get("height", 0) * effective_scale
        frame_color = (180, 180, 190, 255)

        _draw_dashed_line(draw, (fx, fy), (fx + fw, fy), frame_color, width=2)
        _draw_dashed_line(
            draw, (fx + fw, fy), (fx + fw, fy + fh), frame_color, width=2
        )
        _draw_dashed_line(
            draw, (fx + fw, fy + fh), (fx, fy + fh), frame_color, width=2
        )
        _draw_dashed_line(draw, (fx, fy + fh), (fx, fy), frame_color, width=2)

        name = f.get("name") or "Frame"
        f_font = get_font("sans-serif", int(12 * effective_scale), bold=True)
        draw.text(
            (fx + 6 * effective_scale, fy + 4 * effective_scale),
            name,
            fill=(110, 110, 120, 255),
            font=f_font,
        )

    # 2. Render Shapes & Code Blocks
    for s in shapes:
        sx = tx(s.get("x", 0))
        sy = ty(s.get("y", 0))
        sw = s.get("width", 0) * effective_scale
        sh = s.get("height", 0) * effective_scale
        stype = s.get("type")

        custom_data = s.get("customData") or {}

        # Specialized rendering for Code Blocks
        if custom_data.get("type") in ("code_block", "code-block"):
            _render_code_block(draw, s, sx, sy, sw, sh, effective_scale)
            continue

        opacity = s.get("opacity", 100)
        stroke_color = _parse_color(s.get("strokeColor", "#1e1e1e"), opacity)
        bg_fill = _parse_color(s.get("backgroundColor", "transparent"), opacity)
        stroke_w = max(1, int(s.get("strokeWidth", 1) * effective_scale))

        if stype == "rectangle":
            roundness = s.get("roundness")
            radius = 0
            if isinstance(roundness, dict):
                rtype = roundness.get("type")
                if rtype == 3:  # adaptive
                    radius = max(
                        4, min(int(min(sw, sh) * 0.15), int(32 * effective_scale))
                    )
                elif rtype == 2:  # round
                    radius = max(
                        8, min(int(min(sw, sh) * 0.25), int(48 * effective_scale))
                    )

            fill_val = bg_fill if bg_fill[3] > 0 else None
            outline_val = stroke_color if stroke_color[3] > 0 else None

            stroke_style = s.get("strokeStyle", "solid")
            if stroke_style in ("dashed", "dotted") and outline_val:
                if fill_val:
                    if radius > 0:
                        draw.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=radius, fill=fill_val, outline=None)
                    else:
                        draw.rectangle([sx, sy, sx + sw, sy + sh], fill=fill_val, outline=None)
                p_tl = (sx, sy)
                p_tr = (sx + sw, sy)
                p_br = (sx + sw, sy + sh)
                p_bl = (sx, sy + sh)
                _draw_polyline(draw, [p_tl, p_tr, p_br, p_bl, p_tl], fill=outline_val, width=stroke_w, stroke_style=stroke_style)
            elif radius > 0:
                draw.rounded_rectangle(
                    [sx, sy, sx + sw, sy + sh],
                    radius=radius,
                    fill=fill_val,
                    outline=outline_val,
                    width=stroke_w,
                )
            else:
                draw.rectangle(
                    [sx, sy, sx + sw, sy + sh],
                    fill=fill_val,
                    outline=outline_val,
                    width=stroke_w,
                )

        elif stype == "ellipse":
            fill_val = bg_fill if bg_fill[3] > 0 else None
            outline_val = stroke_color if stroke_color[3] > 0 else None
            draw.ellipse(
                [sx, sy, sx + sw, sy + sh],
                fill=fill_val,
                outline=outline_val,
                width=stroke_w,
            )

        elif stype == "diamond":
            top = (sx + sw / 2, sy)
            right = (sx + sw, sy + sh / 2)
            bottom = (sx + sw / 2, sy + sh)
            left = (sx, sy + sh / 2)
            pts = [top, right, bottom, left]

            stroke_style = s.get("strokeStyle", "solid")
            if bg_fill[3] > 0:
                draw.polygon(pts, fill=bg_fill)
            if stroke_color[3] > 0:
                if stroke_style in ("dashed", "dotted"):
                    _draw_polyline(draw, [top, right, bottom, left, top], fill=stroke_color, width=stroke_w, stroke_style=stroke_style)
                else:
                    draw.polygon(pts, outline=stroke_color, width=stroke_w)

    # 3. Render Arrows
    for a in arrows:
        ax = a.get("x", 0)
        ay = a.get("y", 0)
        points = a.get("points") or [[0.0, 0.0], [50.0, 50.0]]
        opacity = a.get("opacity", 100)
        stroke_color = _parse_color(a.get("strokeColor", "#1e1e1e"), opacity)
        stroke_w = max(1, int(a.get("strokeWidth", 2) * effective_scale))

        # Orthogonal routing for elbowed lines/arrows with simple 2-point geometry
        is_elbowed = bool(a.get("elbowed"))
        if is_elbowed and len(points) == 2:
            sb = (a.get("startBinding") or {}).get("elementId")
            eb = (a.get("endBinding") or {}).get("elementId")
            if sb in element_index and eb in element_index:
                from .routing import route_orthogonal_connector
                routed = route_orthogonal_connector(
                    element_index[sb],
                    element_index[eb],
                    obstacles=shapes,
                    clearance=15.0,
                )
                pts = [[pt[0] - ax, pt[1] - ay] for pt in routed]
            else:
                p0, p1 = points[0], points[1]
                dx = float(p1[0]) - float(p0[0])
                dy = float(p1[1]) - float(p0[1])
                if abs(dx) > abs(dy):
                    pts = [
                        p0,
                        [float(p0[0]) + dx / 2.0, float(p0[1])],
                        [float(p0[0]) + dx / 2.0, float(p1[1])],
                        p1,
                    ]
                else:
                    pts = [
                        p0,
                        [float(p0[0]), float(p0[1]) + dy / 2.0],
                        [float(p1[0]), float(p0[1]) + dy / 2.0],
                        p1,
                    ]
        else:
            pts = points

        screen_pts = [(tx(ax + pt[0]), ty(ay + pt[1])) for pt in pts]
        if len(screen_pts) >= 2:
            _draw_polyline(draw, screen_pts, fill=stroke_color, width=stroke_w, stroke_style=a.get("strokeStyle", "solid"))

            # Arrowhead at end
            default_end = "arrow" if a.get("type") == "arrow" else None
            if a.get("endArrowhead", default_end) == "arrow":
                _draw_arrowhead(
                    draw,
                    screen_pts[-1],
                    screen_pts[-2],
                    stroke_color,
                    size=max(10.0, 14.0 * effective_scale),
                )
            # Arrowhead at start
            if a.get("startArrowhead") == "arrow":
                _draw_arrowhead(
                    draw,
                    screen_pts[0],
                    screen_pts[1],
                    stroke_color,
                    size=max(10.0, 14.0 * effective_scale),
                )

    # 4. Render Text & Labels
    for t in texts:
        text_content = t.get("text", "")
        if not text_content:
            continue
        font_size = int(t.get("fontSize", 20) * effective_scale)
        font_fam = (t.get("customData") or {}).get("fontFamily") or t.get("fontFamily")
        font = get_font(font_fam, font_size)
        opacity = t.get("opacity", 100)
        stroke_color = _parse_color(t.get("strokeColor", "#1e1e1e"), opacity)
        text_align = t.get("textAlign", "left")

        container_id = t.get("containerId")
        container = element_index.get(container_id) if container_id else None

        if container:
            ctype = container.get("type")
            if ctype in ("rectangle", "diamond", "ellipse", "frame"):
                cx = float(container.get("x", 0.0)) + float(container.get("width", 0.0)) / 2.0
                cy = float(container.get("y", 0.0)) + float(container.get("height", 0.0)) / 2.0
                scx = tx(cx)
                scy = ty(cy)
                draw.text(
                    (scx, scy),
                    text_content,
                    fill=stroke_color,
                    font=font,
                    anchor="mm",
                    align="center",
                )
            elif ctype in ("arrow", "line"):
                pts = container.get("points") or [
                    [0.0, 0.0],
                    [float(container.get("width", 0.0)), float(container.get("height", 0.0))],
                ]
                if len(pts) > 2 and "x" in t and "y" in t and t.get("width") and t.get("height"):
                    cx = float(t["x"]) + float(t["width"]) / 2.0
                    cy = float(t["y"]) + float(t["height"]) / 2.0
                elif len(pts) >= 2:
                    p0 = pts[0]
                    p1 = pts[-1]
                    cx = float(container.get("x", 0.0)) + (float(p0[0]) + float(p1[0])) / 2.0
                    cy = float(container.get("y", 0.0)) + (float(p0[1]) + float(p1[1])) / 2.0
                else:
                    cx = float(container.get("x", 0.0))
                    cy = float(container.get("y", 0.0))
                scx = tx(cx)
                scy = ty(cy)

                # Mask background behind label to prevent arrow stroke from striking through text
                tb = draw.textbbox((scx, scy), text_content, font=font, anchor="mm", align="center")
                pad = 4.0 * effective_scale
                mask_box = [tb[0] - pad, tb[1] - pad, tb[2] + pad, tb[3] + pad]
                draw.rounded_rectangle(mask_box, radius=max(2, int(3 * effective_scale)), fill=canvas_bg)

                draw.text(
                    (scx, scy),
                    text_content,
                    fill=stroke_color,
                    font=font,
                    anchor="mm",
                    align="center",
                )
            else:
                px = tx(t.get("x", 0))
                py = ty(t.get("y", 0))
                draw.text(
                    (px, py),
                    text_content,
                    fill=stroke_color,
                    font=font,
                    align=text_align,
                )
        else:
            px = tx(t.get("x", 0))
            py = ty(t.get("y", 0))
            draw.text(
                (px, py),
                text_content,
                fill=stroke_color,
                font=font,
                align=text_align,
            )

    # Save to buffer and return bytes and dimensions
    output = io.BytesIO()
    info = PngImagePlugin.PngInfo()
    try:
        info.add_text("application/vnd.excalidraw+json", json.dumps(document, ensure_ascii=False))
    except Exception:
        pass
    image.save(output, format="PNG", pnginfo=info)
    return output.getvalue(), img_w, img_h


def _render_code_block(
    draw: ImageDraw.ImageDraw,
    element: dict[str, Any],
    sx: float,
    sy: float,
    sw: float,
    sh: float,
    scale: float,
):
    """Render a syntax-highlighted code block with window controls and line numbers."""
    custom_data = element.get("customData") or {}
    code = custom_data.get("code", "")
    language = custom_data.get("language", "python")
    title = custom_data.get("title") or f"{language} code"
    theme_name = custom_data.get("theme", "dark")
    font_size = int(custom_data.get("font_size", 14) * scale)
    font_fam = custom_data.get("font_family", "monospace")
    show_line_nums = custom_data.get("line_numbers", True)

    theme = get_theme(theme_name)
    bg_color = _parse_color(theme["bg"])
    border_color = _parse_color(theme["border"])
    title_bg = _parse_color(theme["title_bg"])
    title_color = _parse_color(theme["title_text"])
    gutter_text_color = _parse_color(theme["gutter_text"])
    gutter_border_color = _parse_color(theme["gutter_border"])

    radius = max(6, int(10 * scale))
    # Outer box
    draw.rounded_rectangle(
        [sx, sy, sx + sw, sy + sh],
        radius=radius,
        fill=bg_color,
        outline=border_color,
        width=max(1, int(1 * scale)),
    )

    # Title bar
    title_h = 32.0 * scale
    draw.rounded_rectangle(
        [sx, sy, sx + sw, sy + title_h],
        radius=radius,
        fill=title_bg,
        outline=None,
    )
    # Fill bottom corners of title bar so it flushes with the lower rectangle
    draw.rectangle(
        [sx, sy + title_h - radius, sx + sw, sy + title_h],
        fill=title_bg,
    )
    # Title bar divider
    draw.line(
        [(sx, sy + title_h), (sx + sw, sy + title_h)],
        fill=border_color,
        width=1,
    )

    # Window control buttons (macOS style dots)
    dot_r = 4.5 * scale
    dot_y = sy + title_h / 2
    # Red
    draw.ellipse(
        [sx + 14 * scale - dot_r, dot_y - dot_r, sx + 14 * scale + dot_r, dot_y + dot_r],
        fill=_parse_color("#ff5f56"),
    )
    # Yellow
    draw.ellipse(
        [sx + 26 * scale - dot_r, dot_y - dot_r, sx + 26 * scale + dot_r, dot_y + dot_r],
        fill=_parse_color("#ffbd2e"),
    )
    # Green
    draw.ellipse(
        [sx + 38 * scale - dot_r, dot_y - dot_r, sx + 38 * scale + dot_r, dot_y + dot_r],
        fill=_parse_color("#27c93f"),
    )

    # Title label
    title_font = get_font("sans-serif", int(11 * scale), bold=True)
    draw.text(
        (sx + 54 * scale, sy + (title_h - 11 * scale) / 2),
        title,
        fill=title_color,
        font=title_font,
    )

    # Highlight code lines
    code_lines = highlight_code(code, language, theme_name)
    line_count = len(code_lines)
    digits = len(str(line_count))
    gutter_char_w = 8.0 * scale
    gutter_w = max(32.0 * scale, (digits + 2) * gutter_char_w) if show_line_nums else 0.0

    # Draw gutter line
    if show_line_nums:
        draw.line(
            [(sx + gutter_w, sy + title_h), (sx + gutter_w, sy + sh)],
            fill=gutter_border_color,
            width=1,
        )

    code_font = get_font(font_fam or "monospace", font_size)
    line_h = max(14.0 * scale, font_size * 1.35)

    gutter_font = get_font(font_fam or "monospace", max(9, int(font_size * 0.9)))

    start_y = sy + title_h + 10.0 * scale
    for line_idx, line_tokens in enumerate(code_lines):
        line_y = start_y + line_idx * line_h
        if line_y + line_h > sy + sh:
            break

        # Line number
        if show_line_nums:
            num_str = str(line_idx + 1)
            draw.text(
                (sx + gutter_w - 10.0 * scale, line_y),
                num_str,
                fill=gutter_text_color,
                font=gutter_font,
                anchor="ra",
            )

        # Code tokens
        cur_x = sx + gutter_w + 12.0 * scale
        for token_text, hex_c in line_tokens:
            if cur_x >= sx + sw - 8.0 * scale:
                break
            tok_color = _parse_color(hex_c)
            draw.text((cur_x, line_y), token_text, fill=tok_color, font=code_font)
            cur_x += draw.textlength(token_text, font=code_font)


def render_scene_to_png(
    document: dict[str, Any],
    scale: float = 1.0,
    padding: int = 40,
    background: bool = True,
) -> bytes:
    """Render an Excalidraw document dictionary to PNG image bytes."""
    data, _, _ = render_scene_image(
        document=document,
        scale=scale,
        padding=padding,
        background=background,
    )
    return data
