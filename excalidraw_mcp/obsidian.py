"""Obsidian Excalidraw plugin (.excalidraw.md) serialization and parsing.

Generates and parses Markdown-embedded Excalidraw files compatible with the
Obsidian Excalidraw plugin (zsviczian/obsidian-excalidraw-plugin).
Note: This is specifically for the Obsidian Excalidraw plugin (.excalidraw.md),
NOT the Obsidian Canvas (.canvas) JSON format.
"""

from __future__ import annotations

import json
import re
from typing import Any


OBSIDIAN_EXCALIDRAW_HEADER = """---

excalidraw-plugin: parsed
tags: [excalidraw]

---
==Deconstruct with care==

"""


def serialize_obsidian_markdown(document: dict[str, Any]) -> str:
    """Serialize an Excalidraw document into an Obsidian Excalidraw Markdown file (.excalidraw.md).

    The format embeds the canonical Excalidraw JSON inside a Markdown comment block
    and exposes text elements as Obsidian block references for search and linking.
    """
    elements = document.get("elements", [])
    active_elements = [el for el in elements if not el.get("isDeleted")]

    # Collect text elements for the # Text Elements section
    text_lines: list[str] = []
    for el in active_elements:
        if el.get("type") == "text" and el.get("text"):
            raw_text = str(el["text"]).strip()
            eid = el.get("id", "")
            if raw_text and eid:
                # Sanitize %% delimiters to prevent breaking out of Obsidian comment blocks
                safe_text = raw_text.replace("%%", "% %")
                # Sanitize newlines for block reference format
                single_line = " ".join(safe_text.splitlines())
                text_lines.append(f"{single_line} ^{eid}")

    # Canonical Excalidraw JSON payload
    scene_json = json.dumps(document, indent=2, ensure_ascii=False)

    parts: list[str] = [OBSIDIAN_EXCALIDRAW_HEADER]
    parts.append("%%\n# Text Elements\n")
    if text_lines:
        parts.append("\n".join(text_lines))
        parts.append("\n")
    parts.append("%%\n# Drawing\n```json\n")
    parts.append(scene_json)
    parts.append("\n```\n%%\n")

    return "".join(parts)


def parse_obsidian_markdown(content: str) -> dict[str, Any]:
    """Extract and parse the Excalidraw document JSON from an Obsidian .excalidraw.md file."""
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Obsidian markdown content cannot be empty")

    # Match drawing section if present
    drawing_section = content
    drawing_match = re.search(r"#{1,3}\s*Drawing\s*\n([\s\S]*)", content, re.IGNORECASE)
    if drawing_match:
        drawing_section = drawing_match.group(1)

    # Match the ```json ... ``` code block inside the Drawing section
    match = re.search(r"```(?:json|json:excalidraw|excalidraw)?\s*\n([\s\S]*?)\n```", drawing_section)
    if not match:
        # Fallback to searching entire content
        match = re.search(r"```(?:json|json:excalidraw|excalidraw)?\s*\n([\s\S]*?)\n```", content)

    if not match:
        raise ValueError("Invalid Obsidian Excalidraw file: could not find embedded JSON code block")

    json_str = match.group(1).strip()
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to decode Excalidraw JSON in Obsidian file: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Expected JSON object in Obsidian Drawing block")

    return data
