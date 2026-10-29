"""Rich scene importer supporting JSON, .excalidraw, Obsidian .excalidraw.md, and embedded PNGs."""

import base64
import io
import json
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal

from PIL import Image

from excalidraw_mcp.config import max_scene_bytes, scene_directory
from excalidraw_mcp.document import normalize_document
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.models import new_document, validate_document

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _extract_from_png_bytes(png_bytes: bytes) -> dict[str, Any]:
    """Extract embedded Excalidraw scene JSON from PNG tEXt metadata chunk."""
    try:
        img = Image.open(io.BytesIO(png_bytes))
    except Exception as err:
        raise SceneError(f"Failed to decode PNG image data: {err}") from err

    # Check img.text or img.info for excalidraw chunk key
    candidate_keys = (
        "application/vnd.excalidraw+json",
        "excalidraw",
        "scene",
        "excalidraw_data",
    )
    raw_payload = None
    for k in candidate_keys:
        if k in getattr(img, "text", {}):
            raw_payload = img.text[k]
            break
        if k in getattr(img, "info", {}):
            raw_payload = img.info[k]
            break

    if not raw_payload:
        raise SceneError(
            "PNG image does not contain embedded Excalidraw scene data in its metadata chunks"
        )

    try:
        return json.loads(raw_payload)
    except Exception as err:
        raise SceneError(f"Embedded PNG scene metadata is not valid JSON: {err}") from err


def _extract_from_obsidian_markdown(text: str) -> dict[str, Any]:
    """Extract Excalidraw scene JSON from Obsidian .excalidraw.md format."""
    # Pattern 1: Fenced code block under ## Drawing or # Excalidraw Data
    fenced_match = re.search(
        r"```(?:json|json:excalidraw|excalidraw)\s*(\{.*?\})\s*```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if fenced_match:
        try:
            return json.loads(fenced_match.group(1))
        except Exception:
            pass

    # Pattern 2: Block under ## Drawing
    drawing_match = re.search(r"## Drawing\s*```[a-z:]*\s*(\{.*?\})\s*```", text, re.DOTALL)
    if drawing_match:
        try:
            return json.loads(drawing_match.group(1))
        except Exception:
            pass

    # Pattern 3: Any JSON block containing "elements" and "type": "excalidraw"
    all_json_blocks = re.findall(r"```(?:json)?[ \t]*\n(\{.*?\})\n```", text, re.DOTALL)
    for block in all_json_blocks:
        try:
            parsed = json.loads(block)
            if isinstance(parsed, dict) and ("elements" in parsed or parsed.get("type") == "excalidraw"):
                return parsed
        except Exception:
            continue

    raise SceneError(
        "Could not extract Excalidraw drawing JSON from Obsidian markdown. Missing '```json' drawing block."
    )


def parse_scene_payload(data: str) -> dict[str, Any]:
    """Parse Excalidraw scene document from a path, raw JSON, Obsidian markdown, or PNG data."""
    if not isinstance(data, str) or not data.strip():
        raise SceneError("Import data cannot be empty")

    limit = max_scene_bytes()
    if len(data.encode("utf-8")) > limit:
        raise SceneError(f"Import payload exceeds maximum size ({limit} bytes)")

    cleaned = data.strip()

    # Check 1: Is it raw JSON?
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                # Array of elements passed
                return new_document(parsed)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError as err:
            raise SceneError(f"Invalid JSON payload: {err}") from err

    # Check 2: Is it base64-encoded PNG data?
    if cleaned.startswith("data:image/png;base64,") or cleaned.startswith("iVBORw0KGgo"):
        b64_str = cleaned
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        try:
            png_bytes = base64.b64decode(b64_str)
            if png_bytes.startswith(PNG_SIGNATURE):
                return _extract_from_png_bytes(png_bytes)
        except Exception:
            pass

    # Check 3: Is it inline Obsidian markdown text?
    obsidian_markers = ("# Excalidraw Data", "## Drawing", "excalidraw-plugin", "```json:excalidraw", "```excalidraw")
    if any(marker in cleaned for marker in obsidian_markers):
        return _extract_from_obsidian_markdown(cleaned)

    # Check 4: Is it an existing file path within allowed directories?
    if "\n" not in cleaned and len(cleaned) <= 4096:
        candidate_path = Path(cleaned)
        try:
            if candidate_path.is_file():
                resolved = candidate_path.resolve()
                allowed_roots = [
                    Path(scene_directory()).resolve(),
                    Path.cwd().resolve(),
                ]
                tmp_root = Path(tempfile.gettempdir()).resolve()
                if resolved == tmp_root or resolved.is_relative_to(tmp_root):
                    # In multi-user Unix systems, ensure temporary file is owned by current user
                    if hasattr(os, "getuid"):
                        try:
                            if candidate_path.stat().st_uid != os.getuid():
                                raise SceneError(
                                    f"Access to file '{candidate_path}' is denied; file in temporary directory is not owned by current user"
                                )
                        except OSError as err:
                            raise SceneError(f"Cannot verify ownership of '{candidate_path}': {err}") from err
                    allowed_roots.append(tmp_root)

                if not any(
                    resolved == r or resolved.is_relative_to(r) for r in allowed_roots
                ):
                    raise SceneError(
                        f"Access to file '{candidate_path}' is denied; path must be within the project, scene, or temporary directory"
                    )

                ALLOWED_EXTS = {".excalidraw", ".png", ".md", ".markdown", ".json"}
                if resolved.suffix.lower() not in ALLOWED_EXTS:
                    raise SceneError(
                        f"Unsupported file format '{resolved.suffix}'. Supported extensions: {sorted(ALLOWED_EXTS)}"
                    )

                file_size = candidate_path.stat().st_size
                if file_size > limit:
                    raise SceneError(
                        f"File '{candidate_path}' size ({file_size} bytes) exceeds maximum allowed size ({limit} bytes)"
                    )

                raw_bytes = candidate_path.read_bytes()

                # Check if file is PNG
                if raw_bytes.startswith(PNG_SIGNATURE) or resolved.suffix.lower() == ".png":
                    return _extract_from_png_bytes(raw_bytes)

                # Decode as UTF-8 text
                try:
                    text = raw_bytes.decode("utf-8")
                except UnicodeDecodeError as err:
                    raise SceneError(f"File '{candidate_path}' is not valid UTF-8 text or PNG: {err}") from err

                if resolved.suffix.lower() in (".md", ".markdown") or "# Excalidraw Data" in text:
                    return _extract_from_obsidian_markdown(text)

                try:
                    return json.loads(text)
                except json.JSONDecodeError as err:
                    raise SceneError(f"File '{candidate_path}' contains invalid JSON: {err}") from err
        except OSError as err:
            if isinstance(err, SceneError):
                raise
            raise SceneError(f"Failed to access file '{candidate_path}': {err}") from err

    raise SceneError(
        "Unrecognized import format. Expected file path (.excalidraw, .png, .md), raw JSON, Obsidian markdown, or PNG data."
    )


def import_scene(
    service: Any,
    data: str,
    mode: Literal["replace", "merge"] = "replace",
    offset_x: float = 0.0,
    offset_y: float = 0.0,
) -> dict[str, Any]:
    """Import an Excalidraw scene in 'replace' or 'merge' mode with duplicate-ID prevention."""
    if mode not in ("replace", "merge"):
        raise SceneError("Import mode must be either 'replace' or 'merge'")

    raw_doc = parse_scene_payload(data)

    # Validate structure and ensure it's a valid Excalidraw document
    if not isinstance(raw_doc, dict) or not isinstance(raw_doc.get("elements"), list):
        raise SceneError("Imported document must be an Excalidraw scene object containing an 'elements' list")
    if raw_doc.get("type") not in (None, "excalidraw"):
        raise SceneError(f"Imported document has invalid type '{raw_doc.get('type')}'; expected 'excalidraw'")

    imported_doc = normalize_document(raw_doc)
    incoming_elements = [
        el for el in imported_doc.get("elements", []) if not el.get("isDeleted")
    ]

    if mode == "replace":
        service.state.replace(imported_doc)
        return {
            "status": "imported",
            "mode": "replace",
            "elements_imported": len(incoming_elements),
            "revision": service.state.revision,
        }

    # Merge mode
    def apply_merge(current_document: dict[str, Any]) -> dict[str, Any]:
        existing_elements = current_document.get("elements", [])
        existing_ids = {el["id"] for el in existing_elements if not el.get("isDeleted")}

        id_map: dict[str, str] = {}
        # Identify duplicate IDs and generate collision-free replacements
        for el in incoming_elements:
            orig_id = el["id"]
            if orig_id in existing_ids:
                new_id = f"{el['type']}_{uuid.uuid4().hex[:10]}"
                id_map[orig_id] = new_id

        # Clone and rewrite references
        merged_new_elements = []
        for el in incoming_elements:
            cloned = json.loads(json.dumps(el))
            if cloned["id"] in id_map:
                cloned["id"] = id_map[cloned["id"]]

            # Apply spatial offset
            cloned["x"] += offset_x
            cloned["y"] += offset_y

            # Update containerId
            if cloned.get("containerId") and cloned["containerId"] in id_map:
                cloned["containerId"] = id_map[cloned["containerId"]]

            # Update frameId
            if cloned.get("frameId") and cloned["frameId"] in id_map:
                cloned["frameId"] = id_map[cloned["frameId"]]

            # Update boundElements
            if cloned.get("boundElements"):
                updated_bounds = []
                for b in cloned["boundElements"]:
                    target_id = id_map.get(b.get("id"), b.get("id"))
                    updated_bounds.append({**b, "id": target_id})
                cloned["boundElements"] = updated_bounds

            # Update arrow bindings
            if cloned.get("type") == "arrow":
                for end in ("startBinding", "endBinding"):
                    binding = cloned.get(end)
                    if binding and binding.get("elementId") in id_map:
                        binding["elementId"] = id_map[binding["elementId"]]

            merged_new_elements.append(cloned)

        current_document["elements"].extend(merged_new_elements)

        # Merge files dictionary if present
        if imported_doc.get("files"):
            current_files = current_document.setdefault("files", {})
            current_files.update(imported_doc["files"])

        return {
            "status": "imported",
            "mode": "merge",
            "elements_imported": len(merged_new_elements),
            "total_elements": len(current_document["elements"]),
            "id_mapping": id_map,
        }

    res = service.state.apply(apply_merge)
    return {**res, "revision": service.state.revision}
