"""Standalone vector SVG renderer for Excalidraw scenes.

Generates standards-compliant, scalable vector graphics (SVG) directly from
Excalidraw document dictionaries without requiring headless browsers or Node.js.
Supports all shape types, decision diamonds, rounded rectangles, syntax code blocks,
orthogonal elbowed connectors, modern arrowheads, and multi-line typography.
"""

import html
import math
import re
from typing import Any

from excalidraw_mcp.renderer import _compute_bounds

SAFE_COLOR_PATTERN = re.compile(
    r"^(?:none|transparent|currentColor|#[0-9a-fA-F]{3,8}|(?:rgb|hsl)a?\([^)]+\)|[a-zA-Z]+)$"
)


def _css_font_family(family: int | str | None) -> str:
    """Map Excalidraw font family codes to portable CSS font stacks."""
    if family is None:
        return "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    f_str = str(family).strip().lower()
    if f_str in ("1", "virgil"):
        return "Virgil, Excalifont, 'Segoe Print', 'Comic Sans MS', cursive, sans-serif"
    if f_str in ("5", "excalifont", "handwriting", "hand"):
        return "Excalifont, Virgil, 'Segoe Print', 'Comic Sans MS', cursive, sans-serif"
    if f_str in ("3", "monospace", "mono", "code", "cascadia"):
        return "'Cascadia Code', 'Cascadia Mono', Consolas, 'Courier New', monospace"
    if f_str in ("4", "8", "comic-shanns", "comic", "comic shanns"):
        return "'Comic Shanns', cursive, sans-serif"
    return "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _svg_color(color_str: str | None) -> str:
    """Normalize color string to safe valid SVG color or 'none'."""
    if not color_str or color_str.strip().lower() == "transparent":
        return "none"
    val = color_str.strip()
    if not SAFE_COLOR_PATTERN.match(val):
        return "none"
    return html.escape(val, quote=True)


def _svg_dash_attr(stroke_style: str | None) -> str:
    """Return stroke-dasharray attribute for dashed or dotted strokes."""
    if stroke_style == "dashed":
        return 'stroke-dasharray="8 5"'
    elif stroke_style == "dotted":
        return 'stroke-dasharray="3 3"'
    return ""


def _render_svg_arrowhead(
    tip: tuple[float, float],
    prev_pt: tuple[float, float],
    stroke_color: str,
    arrowhead_type: str = "arrow",
    stroke_w: int = 2,
    size: float = 14.0,
    bg_color: str = "#ffffff",
) -> str:
    """Generate SVG XML elements for an arrowhead or line termination marker."""
    tx, ty = tip
    px, py = prev_pt
    dx = tx - px
    dy = ty - py
    length = math.hypot(dx, dy)
    if length < 1e-4:
        return ""

    ux = dx / length
    uy = dy / length
    nx = -uy
    ny = ux

    head = (arrowhead_type or "arrow").lower()

    if head in ("arrow", "triangle"):
        angle_rad = math.radians(26.0 if head == "arrow" else 30.0)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        lx = tx - size * (ux * cos_a - uy * sin_a)
        ly = ty - size * (uy * cos_a + ux * sin_a)
        rx = tx - size * (ux * cos_a + uy * sin_a)
        ry = ty - size * (uy * cos_a - ux * sin_a)
        pts = f"{tx:.2f},{ty:.2f} {lx:.2f},{ly:.2f} {rx:.2f},{ry:.2f}"
        return f'<polygon points="{pts}" fill="{stroke_color}" stroke="{stroke_color}" stroke-width="1" />\n'

    elif head == "triangle_outline":
        angle_rad = math.radians(30.0)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        lx = tx - size * (ux * cos_a - uy * sin_a)
        ly = ty - size * (uy * cos_a + ux * sin_a)
        rx = tx - size * (ux * cos_a + uy * sin_a)
        ry = ty - size * (uy * cos_a - ux * sin_a)
        pts = f"{tx:.2f},{ty:.2f} {lx:.2f},{ly:.2f} {rx:.2f},{ry:.2f}"
        return f'<polygon points="{pts}" fill="{bg_color}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'

    elif head in ("dot", "circle"):
        r = size * 0.35
        cx = tx - ux * r
        cy = ty - uy * r
        return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{stroke_color}" />\n'

    elif head in ("circle_outline", "dot_outline"):
        r = size * 0.35
        cx = tx - ux * r
        cy = ty - uy * r
        return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{bg_color}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'

    elif head == "bar":
        half_w = size * 0.6
        p1 = (tx + nx * half_w, ty + ny * half_w)
        p2 = (tx - nx * half_w, ty - ny * half_w)
        return f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" stroke="{stroke_color}" stroke-width="{max(2, stroke_w)}" stroke-linecap="round" />\n'

    elif head == "diamond":
        d_len = size * 1.1
        d_hw = size * 0.45
        mid_x = tx - ux * (d_len * 0.5)
        mid_y = ty - uy * (d_len * 0.5)
        back_x = tx - ux * d_len
        back_y = ty - uy * d_len
        pts = (
            f"{tx:.2f},{ty:.2f} "
            f"{mid_x + nx * d_hw:.2f},{mid_y + ny * d_hw:.2f} "
            f"{back_x:.2f},{back_y:.2f} "
            f"{mid_x - nx * d_hw:.2f},{mid_y - ny * d_hw:.2f}"
        )
        return f'<polygon points="{pts}" fill="{stroke_color}" stroke="{stroke_color}" stroke-width="1" />\n'

    elif head == "diamond_outline":
        d_len = size * 1.1
        d_hw = size * 0.45
        mid_x = tx - ux * (d_len * 0.5)
        mid_y = ty - uy * (d_len * 0.5)
        back_x = tx - ux * d_len
        back_y = ty - uy * d_len
        pts = (
            f"{tx:.2f},{ty:.2f} "
            f"{mid_x + nx * d_hw:.2f},{mid_y + ny * d_hw:.2f} "
            f"{back_x:.2f},{back_y:.2f} "
            f"{mid_x - nx * d_hw:.2f},{mid_y - ny * d_hw:.2f}"
        )
        return f'<polygon points="{pts}" fill="{bg_color}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'

    elif head in ("crowfoot_many", "crowfoot_one_or_more"):
        branch_len = size * 0.9
        base_x = tx - ux * branch_len
        base_y = ty - uy * branch_len
        hw = size * 0.5
        top = (tx + nx * hw, ty + ny * hw)
        bot = (tx - nx * hw, ty - ny * hw)
        out = (
            f'<line x1="{base_x:.2f}" y1="{base_y:.2f}" x2="{top[0]:.2f}" y2="{top[1]:.2f}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'
            f'<line x1="{base_x:.2f}" y1="{base_y:.2f}" x2="{bot[0]:.2f}" y2="{bot[1]:.2f}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'
            f'<line x1="{base_x:.2f}" y1="{base_y:.2f}" x2="{tx:.2f}" y2="{ty:.2f}" stroke="{stroke_color}" stroke-width="{stroke_w}" />\n'
        )
        if head == "crowfoot_one_or_more":
            bar_x = base_x - ux * (size * 0.3)
            bar_y = base_y - uy * (size * 0.3)
            p1 = (bar_x + nx * hw, bar_y + ny * hw)
            p2 = (bar_x - nx * hw, bar_y - ny * hw)
            out += f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" stroke="{stroke_color}" stroke-width="{max(2, stroke_w)}" />\n'
        return out

    elif head == "crowfoot_one":
        half_w = size * 0.5
        bar_x = tx - ux * (size * 0.2)
        bar_y = ty - uy * (size * 0.2)
        p1 = (bar_x + nx * half_w, bar_y + ny * half_w)
        p2 = (bar_x - nx * half_w, bar_y - ny * half_w)
        return f'<line x1="{p1[0]:.2f}" y1="{p1[1]:.2f}" x2="{p2[0]:.2f}" y2="{p2[1]:.2f}" stroke="{stroke_color}" stroke-width="{max(2, stroke_w)}" />\n'

    # Standard arrow fallback
    angle_rad = math.radians(26.0)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    lx = tx - size * (ux * cos_a - uy * sin_a)
    ly = ty - size * (uy * cos_a + ux * sin_a)
    rx = tx - size * (ux * cos_a + uy * sin_a)
    ry = ty - size * (uy * cos_a - ux * sin_a)
    pts = f"{tx:.2f},{ty:.2f} {lx:.2f},{ly:.2f} {rx:.2f},{ry:.2f}"
    return f'<polygon points="{pts}" fill="{stroke_color}" stroke="{stroke_color}" stroke-width="1" />\n'


def render_scene_svg(
    document: dict[str, Any],
    padding: int = 40,
    background: bool = True,
) -> tuple[str, float, float]:
    """Render an Excalidraw document dictionary to an SVG string and (width, height).

    Returns:
        (svg_xml_string, svg_width, svg_height)
    """
    padding = max(0, min(200, int(padding)))
    elements = [el for el in document.get("elements", []) if not el.get("isDeleted")]
    app_state = document.get("appState") or {}
    canvas_bg = _svg_color(app_state.get("viewBackgroundColor", "#ffffff"))
    if canvas_bg == "none":
        canvas_bg = "#ffffff"

    min_x, min_y, max_x, max_y = _compute_bounds(elements)
    content_w = max_x - min_x
    content_h = max_y - min_y
    total_w = max(100.0, content_w + padding * 2.0)
    total_h = max(100.0, content_h + padding * 2.0)

    # World to SVG coordinate transformer
    def tx(x: float | int) -> float:
        return float(x) - min_x + padding

    def ty(y: float | int) -> float:
        return float(y) - min_y + padding

    element_index = {el["id"]: el for el in elements if "id" in el}

    frames = [el for el in elements if el.get("type") == "frame"]
    shapes = [
        el
        for el in elements
        if el.get("type") in ("rectangle", "ellipse", "diamond")
    ]
    arrows = [el for el in elements if el.get("type") in ("arrow", "line")]
    texts = [el for el in elements if el.get("type") == "text"]

    svg_parts: list[str] = []
    svg_parts.append('<?xml version="1.0" encoding="UTF-8"?>\n')
    svg_parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.2f} {total_h:.2f}" '
        f'width="{total_w:.2f}" height="{total_h:.2f}">\n'
    )
    svg_parts.append(
        "  <defs>\n"
        "    <style>\n"
        "      .excalidraw-text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }\n"
        "    </style>\n"
        "  </defs>\n"
    )

    if background:
        svg_parts.append(
            f'  <rect width="{total_w:.2f}" height="{total_h:.2f}" fill="{canvas_bg}" />\n'
        )

    # 1. Frames
    for f in frames:
        fx, fy = tx(f.get("x", 0)), ty(f.get("y", 0))
        fw = float(f.get("width", 0))
        fh = float(f.get("height", 0))
        name = f.get("name") or "Frame"
        svg_parts.append(
            f'  <rect x="{fx:.2f}" y="{fy:.2f}" width="{fw:.2f}" height="{fh:.2f}" '
            f'fill="none" stroke="#6e6e78" stroke-width="2" stroke-dasharray="8 5" rx="4" />\n'
        )
        svg_parts.append(
            f'  <text x="{fx + 8:.2f}" y="{fy + 18:.2f}" fill="#6e6e78" font-size="12" '
            f'font-family="sans-serif" font-weight="bold">{html.escape(name)}</text>\n'
        )

    # 2. Shapes & Code Blocks
    for s in shapes:
        sx, sy = tx(s.get("x", 0)), ty(s.get("y", 0))
        sw = float(s.get("width", 0))
        sh = float(s.get("height", 0))
        stype = s.get("type")
        custom_data = s.get("customData") or {}

        opacity = float(s.get("opacity", 100)) / 100.0
        opacity_attr = f'opacity="{opacity:.2f}"' if opacity < 1.0 else ""
        stroke = _svg_color(s.get("strokeColor", "#1e1e1e"))
        fill = _svg_color(s.get("backgroundColor", "none"))
        stroke_w = max(1, int(s.get("strokeWidth", 1)))
        dash = _svg_dash_attr(s.get("strokeStyle"))

        # Specialized rendering for Code Blocks
        if custom_data.get("type") in ("code_block", "code-block"):
            from excalidraw_mcp.code_blocks import get_theme, highlight_code

            code = custom_data.get("code", "")
            language = custom_data.get("language", "python")
            title = custom_data.get("title") or f"{language} code"
            theme_name = custom_data.get("theme", "dark")
            theme = get_theme(theme_name)
            title_h = 32.0

            # Outer box & title bar
            svg_parts.append(
                f'  <rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" height="{sh:.2f}" '
                f'rx="8" fill="{theme["bg"]}" stroke="{theme["border"]}" stroke-width="1" />\n'
            )
            svg_parts.append(
                f'  <path d="M {sx:.2f} {sy + 8:.2f} A 8 8 0 0 1 {sx + 8:.2f} {sy:.2f} '
                f'L {sx + sw - 8:.2f} {sy:.2f} A 8 8 0 0 1 {sx + sw:.2f} {sy + 8:.2f} '
                f'L {sx + sw:.2f} {sy + title_h:.2f} L {sx:.2f} {sy + title_h:.2f} Z" '
                f'fill="{theme["title_bg"]}" />\n'
            )
            svg_parts.append(
                f'  <line x1="{sx:.2f}" y1="{sy + title_h:.2f}" x2="{sx + sw:.2f}" y2="{sy + title_h:.2f}" '
                f'stroke="{theme["border"]}" stroke-width="1" />\n'
            )
            # Window control dots
            svg_parts.append(f'  <circle cx="{sx + 14:.2f}" cy="{sy + 16:.2f}" r="4.5" fill="#ff5f56" />\n')
            svg_parts.append(f'  <circle cx="{sx + 26:.2f}" cy="{sy + 16:.2f}" r="4.5" fill="#ffbd2e" />\n')
            svg_parts.append(f'  <circle cx="{sx + 38:.2f}" cy="{sy + 16:.2f}" r="4.5" fill="#27c93f" />\n')
            # Title text
            svg_parts.append(
                f'  <text x="{sx + 54:.2f}" y="{sy + 20:.2f}" fill="{theme["title_text"]}" '
                f'font-size="11" font-family="sans-serif" font-weight="bold">{html.escape(title)}</text>\n'
            )

            # Code text
            font_size = int(custom_data.get("font_size", 14))
            line_height = font_size * 1.45
            tokens_by_line = highlight_code(code, language, theme_name)
            for l_idx, line_tokens in enumerate(tokens_by_line):
                curr_y = sy + title_h + 16.0 + (l_idx + 1) * line_height - 4.0
                curr_x = sx + 48.0
                # Line number
                svg_parts.append(
                    f'  <text x="{sx + 32:.2f}" y="{curr_y:.2f}" text-anchor="end" '
                    f'fill="{theme["gutter_text"]}" font-size="{font_size}" font-family="monospace">{l_idx + 1}</text>\n'
                )
                for token_text, token_color in line_tokens:
                    escaped_txt = html.escape(token_text).replace(" ", "&#160;")
                    svg_parts.append(
                        f'  <text x="{curr_x:.2f}" y="{curr_y:.2f}" fill="{token_color}" '
                        f'font-size="{font_size}" font-family="monospace">{escaped_txt}</text>\n'
                    )
                    curr_x += len(token_text) * (font_size * 0.6)
            continue

        if stype == "rectangle":
            roundness = s.get("roundness")
            radius = 0
            if isinstance(roundness, dict):
                rtype = roundness.get("type")
                if rtype == 3:  # adaptive
                    radius = max(4, min(int(min(sw, sh) * 0.15), 32))
                elif rtype == 2:  # round
                    radius = max(8, min(int(min(sw, sh) * 0.25), 48))
            svg_parts.append(
                f'  <rect x="{sx:.2f}" y="{sy:.2f}" width="{sw:.2f}" height="{sh:.2f}" '
                f'rx="{radius}" ry="{radius}" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{stroke_w}" {dash} {opacity_attr} />\n'
            )
        elif stype == "ellipse":
            cx = sx + sw / 2.0
            cy = sy + sh / 2.0
            rx = sw / 2.0
            ry = sh / 2.0
            svg_parts.append(
                f'  <ellipse cx="{cx:.2f}" cy="{cy:.2f}" rx="{rx:.2f}" ry="{ry:.2f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}" {dash} {opacity_attr} />\n'
            )
        elif stype == "diamond":
            top = f"{sx + sw / 2.0:.2f},{sy:.2f}"
            right = f"{sx + sw:.2f},{sy + sh / 2.0:.2f}"
            bottom = f"{sx + sw / 2.0:.2f},{sy + sh:.2f}"
            left = f"{sx:.2f},{sy + sh / 2.0:.2f}"
            pts = f"{top} {right} {bottom} {left}"
            svg_parts.append(
                f'  <polygon points="{pts}" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{stroke_w}" {dash} {opacity_attr} />\n'
            )

    # 3. Connectors & Arrows
    for a in arrows:
        ax, ay = a.get("x", 0), a.get("y", 0)
        points = a.get("points") or [[0.0, 0.0], [50.0, 50.0]]
        opacity = float(a.get("opacity", 100)) / 100.0
        opacity_attr = f'opacity="{opacity:.2f}"' if opacity < 1.0 else ""
        stroke = _svg_color(a.get("strokeColor", "#1e1e1e"))
        stroke_w = max(1, int(a.get("strokeWidth", 2)))
        dash = _svg_dash_attr(a.get("strokeStyle"))

        # Orthogonal routing for elbowed connectors
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
                arrow_pts: list[Any] = [[pt[0] - ax, pt[1] - ay] for pt in routed]
            else:
                p0, p1 = points[0], points[1]
                dx = float(p1[0]) - float(p0[0])
                dy = float(p1[1]) - float(p0[1])
                if abs(dx) > abs(dy):
                    arrow_pts = [
                        p0,
                        [float(p0[0]) + dx / 2.0, float(p0[1])],
                        [float(p0[0]) + dx / 2.0, float(p1[1])],
                        p1,
                    ]
                else:
                    arrow_pts = [
                        p0,
                        [float(p0[0]), float(p0[1]) + dy / 2.0],
                        [float(p1[0]), float(p0[1]) + dy / 2.0],
                        p1,
                    ]
        else:
            arrow_pts = points

        screen_pts = [(tx(ax + pt[0]), ty(ay + pt[1])) for pt in arrow_pts]
        if len(screen_pts) >= 2:
            pts_str = " ".join(f"{pt[0]:.2f},{pt[1]:.2f}" for pt in screen_pts)
            svg_parts.append(
                f'  <polyline points="{pts_str}" fill="none" stroke="{stroke}" '
                f'stroke-width="{stroke_w}" stroke-linecap="round" stroke-linejoin="round" '
                f'{dash} {opacity_attr} />\n'
            )

            # Arrowhead at end
            default_end = "arrow" if a.get("type") == "arrow" else None
            end_head = a.get("endArrowhead", default_end)
            if end_head:
                svg_parts.append(
                    _render_svg_arrowhead(
                        screen_pts[-1],
                        screen_pts[-2],
                        stroke,
                        arrowhead_type=end_head,
                        stroke_w=stroke_w,
                        size=14.0,
                        bg_color=canvas_bg,
                    )
                )
            # Arrowhead at start
            start_head = a.get("startArrowhead")
            if start_head:
                svg_parts.append(
                    _render_svg_arrowhead(
                        screen_pts[0],
                        screen_pts[1],
                        stroke,
                        arrowhead_type=start_head,
                        stroke_w=stroke_w,
                        size=14.0,
                        bg_color=canvas_bg,
                    )
                )

    # 4. Text & Labels
    for t in texts:
        text_content = t.get("text", "")
        if not text_content:
            continue
        font_size = int(t.get("fontSize", 20))
        font_fam = (t.get("customData") or {}).get("fontFamily") or t.get("fontFamily")
        css_font = _css_font_family(font_fam)
        opacity = float(t.get("opacity", 100)) / 100.0
        opacity_attr = f'opacity="{opacity:.2f}"' if opacity < 1.0 else ""
        stroke = _svg_color(t.get("strokeColor", "#1e1e1e"))
        lines = text_content.splitlines() or [""]
        line_height = font_size * 1.25

        container_id = t.get("containerId")
        container = element_index.get(container_id) if container_id else None

        if container:
            ctype = container.get("type")
            if ctype in ("rectangle", "diamond", "ellipse", "frame"):
                cx = tx(float(container.get("x", 0)) + float(container.get("width", 0)) / 2.0)
                cy = ty(float(container.get("y", 0)) + float(container.get("height", 0)) / 2.0)
                total_text_h = len(lines) * line_height
                start_y = cy - total_text_h / 2.0 + font_size * 0.85
                svg_parts.append(
                    f'  <text x="{cx:.2f}" y="{start_y:.2f}" text-anchor="middle" '
                    f'fill="{stroke}" font-size="{font_size}" font-family="{css_font}" {opacity_attr}>\n'
                )
                for idx, line in enumerate(lines):
                    dy_attr = f'dy="{line_height:.2f}"' if idx > 0 else 'dy="0"'
                    svg_parts.append(f'    <tspan x="{cx:.2f}" {dy_attr}>{html.escape(line)}</tspan>\n')
                svg_parts.append("  </text>\n")
            elif ctype in ("arrow", "line"):
                container_pts = container.get("points") or [
                    [0.0, 0.0],
                    [float(container.get("width", 0.0)), float(container.get("height", 0.0))],
                ]
                if len(container_pts) >= 2:
                    p0 = container_pts[0]
                    p1 = container_pts[-1]
                    cx = tx(float(container.get("x", 0.0)) + (float(p0[0]) + float(p1[0])) / 2.0)
                    cy = ty(float(container.get("y", 0.0)) + (float(p0[1]) + float(p1[1])) / 2.0)
                else:
                    cx = tx(container.get("x", 0.0))
                    cy = ty(container.get("y", 0.0))

                # Background mask rectangle behind label text
                approx_w = max(len(line) for line in lines) * font_size * 0.6 + 12.0
                approx_h = len(lines) * line_height + 6.0
                svg_parts.append(
                    f'  <rect x="{cx - approx_w / 2.0:.2f}" y="{cy - approx_h / 2.0:.2f}" '
                    f'width="{approx_w:.2f}" height="{approx_h:.2f}" rx="4" fill="{canvas_bg}" />\n'
                )
                start_y = cy - (len(lines) * line_height) / 2.0 + font_size * 0.85
                svg_parts.append(
                    f'  <text x="{cx:.2f}" y="{start_y:.2f}" text-anchor="middle" '
                    f'fill="{stroke}" font-size="{font_size}" font-family="{css_font}" {opacity_attr}>\n'
                )
                for idx, line in enumerate(lines):
                    dy_attr = f'dy="{line_height:.2f}"' if idx > 0 else 'dy="0"'
                    svg_parts.append(f'    <tspan x="{cx:.2f}" {dy_attr}>{html.escape(line)}</tspan>\n')
                svg_parts.append("  </text>\n")
            else:
                px = tx(t.get("x", 0))
                py = ty(t.get("y", 0)) + font_size * 0.85
                svg_parts.append(
                    f'  <text x="{px:.2f}" y="{py:.2f}" fill="{stroke}" '
                    f'font-size="{font_size}" font-family="{css_font}" {opacity_attr}>\n'
                )
                for idx, line in enumerate(lines):
                    dy_attr = f'dy="{line_height:.2f}"' if idx > 0 else 'dy="0"'
                    svg_parts.append(f'    <tspan x="{px:.2f}" {dy_attr}>{html.escape(line)}</tspan>\n')
                svg_parts.append("  </text>\n")
        else:
            px = tx(t.get("x", 0))
            py = ty(t.get("y", 0)) + font_size * 0.85
            svg_parts.append(
                f'  <text x="{px:.2f}" y="{py:.2f}" fill="{stroke}" '
                f'font-size="{font_size}" font-family="{css_font}" {opacity_attr}>\n'
            )
            for idx, line in enumerate(lines):
                dy_attr = f'dy="{line_height:.2f}"' if idx > 0 else 'dy="0"'
                svg_parts.append(f'    <tspan x="{px:.2f}" {dy_attr}>{html.escape(line)}</tspan>\n')
            svg_parts.append("  </text>\n")

    svg_parts.append("</svg>\n")
    return "".join(svg_parts), total_w, total_h
