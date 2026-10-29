"""Code block element creation, syntax highlighting, and formatting."""

import uuid
from typing import Any

from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer  # type: ignore[import-untyped]
from pygments.styles import get_style_by_name  # type: ignore[import-untyped]

from excalidraw_mcp.elements import bind_text, text
from excalidraw_mcp.fonts import get_font, registry

THEMES = {
    "dark": {
        "bg": "#1e1e1e",
        "border": "#3c3c3c",
        "title_bg": "#252526",
        "title_text": "#cccccc",
        "gutter_text": "#858585",
        "gutter_border": "#333333",
        "default_text": "#d4d4d4",
        "pygments_style": "monokai",
    },
    "monokai": {
        "bg": "#272822",
        "border": "#3e3d32",
        "title_bg": "#1e1f1c",
        "title_text": "#75715e",
        "gutter_text": "#75715e",
        "gutter_border": "#3e3d32",
        "default_text": "#f8f8f2",
        "pygments_style": "monokai",
    },
    "github-dark": {
        "bg": "#0d1117",
        "border": "#30363d",
        "title_bg": "#161b22",
        "title_text": "#8b949e",
        "gutter_text": "#6e7681",
        "gutter_border": "#21262d",
        "default_text": "#c9d1d9",
        "pygments_style": "github-dark",
    },
    "light": {
        "bg": "#f6f8fa",
        "border": "#d0d7de",
        "title_bg": "#eaeef2",
        "title_text": "#57606a",
        "gutter_text": "#8c959f",
        "gutter_border": "#d8dee4",
        "default_text": "#24292f",
        "pygments_style": "default",
    },
    "solarized-dark": {
        "bg": "#002b36",
        "border": "#073642",
        "title_bg": "#073642",
        "title_text": "#93a1a1",
        "gutter_text": "#586e75",
        "gutter_border": "#073642",
        "default_text": "#839496",
        "pygments_style": "solarized-dark",
    },
}


def get_theme(name: str | None) -> dict[str, str]:
    """Retrieve theme styling dictionary with fallback to 'dark'."""
    if not name:
        return THEMES["dark"]
    key = name.strip().lower()
    return THEMES.get(key, THEMES["dark"])


def highlight_code(code: str, language: str = "python", theme_name: str = "dark"):
    """Tokenize and syntax-highlight code using Pygments.

    Returns:
        List of lines, where each line is a list of (token_text, hex_color).
    """
    theme = get_theme(theme_name)
    try:
        lexer = get_lexer_by_name(language.strip().lower(), stripall=False)
    except Exception:
        try:
            lexer = guess_lexer(code)
        except Exception:
            lexer = TextLexer()

    try:
        style = get_style_by_name(theme["pygments_style"])
    except Exception:
        style = get_style_by_name("default")

    default_color = theme["default_text"]
    raw_tokens = list(lexer.get_tokens(code))

    lines: list[list[tuple[str, str]]] = [[]]
    for token, text_val in raw_tokens:
        st = style.style_for_token(token)
        hex_c = f"#{st['color']}" if st.get("color") else default_color

        sub_parts = text_val.split("\n")
        for idx, part in enumerate(sub_parts):
            if idx > 0:
                lines.append([])
            if part:
                lines[-1].append((part, hex_c))

    # Strip trailing empty line produced by Pygments' trailing newline
    if len(lines) > 1 and not lines[-1]:
        lines.pop()

    return lines


def calculate_code_block_dimensions(
    code: str,
    font_size: int = 14,
    font_family: str | None = "monospace",
    line_numbers: bool = True,
    title: str | None = None,
    explicit_w: float | None = None,
    explicit_h: float | None = None,
) -> tuple[float, float, float, float]:
    """Calculate dimensions (width, height, gutter_width, line_height)."""
    font = get_font(font_family or "monospace", size=font_size)
    char_w, line_h = registry.get_char_dimensions(font)

    lines = code.split("\n")
    line_count = max(1, len(lines))
    max_line_len = max((len(line) for line in lines), default=1)

    gutter_w = 0.0
    if line_numbers:
        digits = len(str(line_count))
        gutter_w = max(32.0, (digits + 2) * char_w)

    title_h = 34.0 if title is not None else 16.0
    content_w = gutter_w + (max_line_len + 3) * char_w + 32.0
    content_h = title_h + (line_count + 1) * line_h + 20.0

    width = explicit_w if explicit_w is not None and explicit_w > 0 else max(260.0, content_w)
    height = explicit_h if explicit_h is not None and explicit_h > 0 else max(100.0, content_h)

    return width, height, gutter_w, line_h


def create_code_block(
    x: float,
    y: float,
    code: str,
    language: str = "python",
    title: str | None = None,
    theme: str = "dark",
    font_size: int = 14,
    font_family: str | None = "monospace",
    line_numbers: bool = True,
    w: float | None = None,
    h: float | None = None,
    frame_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create Excalidraw element pair (container rectangle + paired monospace text).

    Returns:
        (container_element, text_element)
    """
    theme_cfg = get_theme(theme)
    width, height, gutter_w, line_h = calculate_code_block_dimensions(
        code=code,
        font_size=font_size,
        font_family=font_family,
        line_numbers=line_numbers,
        title=title,
        explicit_w=w,
        explicit_h=h,
    )

    container_id = str(uuid.uuid4())
    container = {
        "id": container_id,
        "type": "rectangle",
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": theme_cfg["border"],
        "backgroundColor": theme_cfg["bg"],
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": frame_id,
        "roundness": {"type": 3},  # Adaptive rounded corners
        "seed": 1,
        "version": 1,
        "versionNonce": 1,
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        "customData": {
            "type": "code_block",
            "language": language,
            "code": code,
            "title": title or f"{language} code",
            "theme": theme,
            "font_size": font_size,
            "font_family": font_family or "monospace",
            "line_numbers": line_numbers,
        },
    }

    # Format text with line numbers for Excalidraw editor compatibility
    lines = code.split("\n")
    digits = len(str(len(lines)))
    if line_numbers:
        formatted_lines = [
            f"{str(i + 1).rjust(digits)}  {line}" for i, line in enumerate(lines)
        ]
        text_content = "\n".join(formatted_lines)
    else:
        text_content = code

    # Text element placed cleanly within container body
    text_x = x + (gutter_w if not line_numbers else 16.0)
    text_y = y + 40.0
    text_el = text(
        text_x,
        text_y,
        text_content,
        fontSize=font_size,
        strokeColor=theme_cfg["default_text"],
        frame_id=frame_id,
    )
    # Use Cascadia/Monospace font in Excalidraw standard schema
    text_el["fontFamily"] = 3
    text_el["textAlign"] = "left"
    text_el["verticalAlign"] = "top"
    bind_text(text_el, container)

    return container, text_el
