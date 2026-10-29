"""Storage configuration with no import-time filesystem writes."""

import os
import sys
from pathlib import Path


DEFAULT_MAX_SCENE_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_EXPORT_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_ELEMENTS = 10_000
DEFAULT_MAX_HISTORY_BYTES = 100 * 1024 * 1024


def scene_directory():
    configured = os.environ.get("EXCALIDRAW_SCENE_DIR")
    root = Path(configured).expanduser() if configured else default_scene_directory()
    if not root.is_absolute():
        raise ValueError("EXCALIDRAW_SCENE_DIR must be an absolute path")
    return root


def export_directory():
    configured = os.environ.get("EXCALIDRAW_EXPORT_DIR")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_absolute():
            raise ValueError("EXCALIDRAW_EXPORT_DIR must be an absolute path")
        return root
    return scene_directory() / "exports"


def default_scene_directory():
    """Return a writable per-user data location without touching the filesystem."""
    if sys.platform == "darwin":
        data_home = Path.home() / "Library" / "Application Support"
    elif sys.platform.startswith("win"):
        configured = os.environ.get("APPDATA")
        data_home = (
            Path(configured).expanduser()
            if configured
            else Path.home() / "AppData" / "Roaming"
        )
        if not data_home.is_absolute():
            raise ValueError("APPDATA must be an absolute path")
    else:
        configured = os.environ.get("XDG_DATA_HOME")
        data_home = (
            Path(configured).expanduser()
            if configured
            else Path.home() / ".local" / "share"
        )
        if not data_home.is_absolute():
            raise ValueError("XDG_DATA_HOME must be an absolute path")
    return data_home / "excalidraw-mcp" / "scenes"


def history_limit():
    return _bounded_integer("EXCALIDRAW_HISTORY_LIMIT", 20, 1, 100)


def max_history_bytes():
    """Maximum approximate serialized bytes retained across undo snapshots."""
    return _bounded_integer(
        "EXCALIDRAW_MAX_HISTORY_BYTES",
        DEFAULT_MAX_HISTORY_BYTES,
        1_024,
        500 * 1024 * 1024,
    )


def max_scene_bytes():
    """Maximum UTF-8 size accepted for one persisted scene."""
    return _bounded_integer(
        "EXCALIDRAW_MAX_SCENE_BYTES", DEFAULT_MAX_SCENE_BYTES, 1_024, 100 * 1024 * 1024
    )


def max_export_bytes():
    """Maximum UTF-8 size returned by an MCP scene export or resource."""
    return _bounded_integer(
        "EXCALIDRAW_MAX_EXPORT_BYTES",
        DEFAULT_MAX_EXPORT_BYTES,
        1_024,
        100 * 1024 * 1024,
    )


def max_elements():
    """Maximum number of elements retained in one active or persisted scene."""
    return _bounded_integer("EXCALIDRAW_MAX_ELEMENTS", DEFAULT_MAX_ELEMENTS, 1, 100_000)


def configured_toolset() -> str:
    """Return the active toolset mode ('core' or 'full'), defaulting to 'core'."""
    raw = os.environ.get("EXCALIDRAW_TOOLSET", "core").strip().lower()
    return raw if raw in ("core", "full") else "core"


def _bounded_integer(name, default, minimum, maximum):
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value
