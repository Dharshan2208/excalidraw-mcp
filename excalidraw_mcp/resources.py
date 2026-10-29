"""Unified resource retrieval interface for Excalidraw scenes, libraries, themes, and elements."""

import json
import re
from pathlib import Path
from typing import Any

from excalidraw_mcp.config import scene_directory
from excalidraw_mcp.errors import SceneError
from excalidraw_mcp.scene import load_scene

THEMES: dict[str, dict[str, Any]] = {
    "default": {
        "name": "default",
        "description": "Standard Excalidraw aesthetic with hand-drawn white canvas",
        "backgroundColor": "#ffffff",
        "strokeColor": "#1e1e1e",
        "accentColor": "#1971c2",
        "palette": ["#1e1e1e", "#e03131", "#2f9e44", "#1971c2", "#f08c00", "#9c36b5"],
        "fillStyles": ["solid", "hachure"],
        "fontFamily": "sans-serif",
    },
    "dark": {
        "name": "dark",
        "description": "Modern dark canvas with slate elements and vibrant accents",
        "backgroundColor": "#121212",
        "strokeColor": "#f8f9fa",
        "accentColor": "#339af0",
        "palette": ["#f8f9fa", "#ff6b6b", "#51cf66", "#339af0", "#fcc419", "#cc5de8"],
        "fillStyles": ["solid", "hachure"],
        "fontFamily": "sans-serif",
    },
    "light": {
        "name": "light",
        "description": "Clean, minimal light theme with soft pastel card fills",
        "backgroundColor": "#f8f9fa",
        "strokeColor": "#212529",
        "accentColor": "#228be6",
        "palette": ["#212529", "#fa5252", "#40c057", "#228be6", "#fab005", "#be4bdb"],
        "fillStyles": ["solid"],
        "fontFamily": "sans-serif",
    },
    "monokai": {
        "name": "monokai",
        "description": "Developer dark theme with high-contrast syntax highlighting tones",
        "backgroundColor": "#272822",
        "strokeColor": "#f8f8f2",
        "accentColor": "#66d9ef",
        "palette": ["#f8f8f2", "#f92672", "#a6e22e", "#66d9ef", "#fd971f", "#ae81ff"],
        "fillStyles": ["solid"],
        "fontFamily": "monospace",
    },
    "nord": {
        "name": "nord",
        "description": "Arctic, north-bluish palette with clean contrast",
        "backgroundColor": "#2e3440",
        "strokeColor": "#eceff4",
        "accentColor": "#88c0d0",
        "palette": ["#eceff4", "#bf616a", "#a3be8c", "#88c0d0", "#ebcb8b", "#b48ead"],
        "fillStyles": ["solid"],
        "fontFamily": "sans-serif",
    },
    "solarized-dark": {
        "name": "solarized-dark",
        "description": "Classic precision solarized dark palette",
        "backgroundColor": "#002b36",
        "strokeColor": "#839496",
        "accentColor": "#268bd2",
        "palette": ["#839496", "#dc322f", "#859900", "#268bd2", "#b58900", "#d33682"],
        "fillStyles": ["solid"],
        "fontFamily": "monospace",
    },
    "solarized-light": {
        "name": "solarized-light",
        "description": "Classic precision solarized light palette",
        "backgroundColor": "#fdf6e3",
        "strokeColor": "#657b83",
        "accentColor": "#268bd2",
        "palette": ["#657b83", "#dc322f", "#859900", "#268bd2", "#b58900", "#d33682"],
        "fillStyles": ["solid"],
        "fontFamily": "sans-serif",
    },
}

LIBRARIES: dict[str, dict[str, Any]] = {
    "architecture": {
        "name": "architecture",
        "description": "Core software architecture components and tiers",
        "items": [
            {
                "name": "Web Client",
                "type": "rectangle",
                "width": 140,
                "height": 70,
                "label": "Web Client\n(React / SPA)",
                "backgroundColor": "#e7f5ff",
                "strokeColor": "#1971c2",
            },
            {
                "name": "API Gateway",
                "type": "rectangle",
                "width": 140,
                "height": 70,
                "label": "API Gateway\n(Reverse Proxy)",
                "backgroundColor": "#e3fafc",
                "strokeColor": "#0c8599",
            },
            {
                "name": "Microservice",
                "type": "rectangle",
                "width": 140,
                "height": 70,
                "label": "Core Service\n(gRPC / HTTP)",
                "backgroundColor": "#f3f0ff",
                "strokeColor": "#5f3dc4",
            },
            {
                "name": "Database",
                "type": "rectangle",
                "width": 130,
                "height": 70,
                "label": "PostgreSQL DB\n(Primary)",
                "backgroundColor": "#ebfbee",
                "strokeColor": "#2f9e44",
            },
            {
                "name": "Redis Cache",
                "type": "rectangle",
                "width": 130,
                "height": 70,
                "label": "Redis Cache\n(In-Memory)",
                "backgroundColor": "#ebfbee",
                "strokeColor": "#2f9e44",
            },
            {
                "name": "Message Queue",
                "type": "rectangle",
                "width": 140,
                "height": 70,
                "label": "Kafka / SQS\n(Event Stream)",
                "backgroundColor": "#fff4e6",
                "strokeColor": "#d9480f",
            },
        ],
    },
    "flowchart": {
        "name": "flowchart",
        "description": "Standard flow diagram symbols",
        "items": [
            {
                "name": "Process",
                "type": "rectangle",
                "width": 140,
                "height": 60,
                "label": "Process Step",
                "backgroundColor": "#ffffff",
                "strokeColor": "#1e1e1e",
            },
            {
                "name": "Decision",
                "type": "diamond",
                "width": 120,
                "height": 70,
                "label": "Condition?",
                "backgroundColor": "#fff9db",
                "strokeColor": "#f08c00",
            },
            {
                "name": "Terminal",
                "type": "ellipse",
                "width": 90,
                "height": 90,
                "label": "Start / End",
                "backgroundColor": "#ebfbee",
                "strokeColor": "#2f9e44",
            },
        ],
    },
    "cloud": {
        "name": "cloud",
        "description": "Cloud infrastructure and networking components",
        "items": [
            {
                "name": "VPC Network Frame",
                "type": "frame",
                "width": 500,
                "height": 350,
                "name": "VPC Network (10.0.0.0/16)",
            },
            {
                "name": "Load Balancer",
                "type": "rectangle",
                "width": 140,
                "height": 60,
                "label": "Application\nLoad Balancer",
                "backgroundColor": "#e7f5ff",
                "strokeColor": "#1971c2",
            },
            {
                "name": "Serverless Function",
                "type": "rectangle",
                "width": 130,
                "height": 60,
                "label": "AWS Lambda\nFunction",
                "backgroundColor": "#fff4e6",
                "strokeColor": "#d9480f",
            },
        ],
    },
}


def parse_resource_uri(uri: str) -> tuple[str, str]:
    """Parse an excalidraw://resource_type/identifier URI."""
    match = re.match(r"^excalidraw://([a-zA-Z0-9_-]+)/?(.*)$", uri.strip())
    if not match:
        raise SceneError(f"Invalid resource URI: '{uri}'. Expected 'excalidraw://<type>/<identifier>'")
    res_type = match.group(1).lower()
    # Normalize plural aliases: scenes -> scene, themes -> theme, etc.
    type_map = {
        "scenes": "scene",
        "themes": "theme",
        "libraries": "library",
        "elements": "element",
    }
    res_type = type_map.get(res_type, res_type)
    ident = match.group(2).strip().strip("/")
    return res_type, ident


def get_resource(
    service: Any,
    uri: str | None = None,
    resource_type: str | None = None,
    identifier: str | None = None,
) -> dict[str, Any]:
    """Unified resource retrieval for scenes, libraries, themes, and elements."""
    if uri:
        res_type, ident = parse_resource_uri(uri)
    elif resource_type:
        res_type = resource_type.strip().lower()
        type_map = {
            "scenes": "scene",
            "themes": "theme",
            "libraries": "library",
            "elements": "element",
        }
        res_type = type_map.get(res_type, res_type)
        ident = (identifier or "").strip()
    else:
        raise SceneError("Provide either 'uri' or 'resource_type' to get_resource")

    if res_type == "scene":
        if not ident or ident in ("active", "current"):
            doc, rev = service.state.snapshot()
            active_els = [el for el in doc.get("elements", []) if not el.get("isDeleted")]
            return {
                "resource_type": "scene",
                "identifier": "active",
                "name": "active",
                "element_count": len(active_els),
                "document": doc,
                "revision": rev,
            }
        # Saved scene from disk
        doc = load_scene(ident)
        active_els = [el for el in doc.get("elements", []) if not el.get("isDeleted")]
        return {
            "resource_type": "scene",
            "identifier": ident,
            "name": ident,
            "element_count": len(active_els),
            "document": doc,
            "revision": service.state.revision,
        }

    elif res_type == "theme":
        theme_key = ident.lower() if ident else "default"
        if theme_key not in THEMES:
            raise SceneError(
                f"Theme '{theme_key}' not found. Available themes: {list(THEMES.keys())}"
            )
        return {
            "resource_type": "theme",
            "identifier": theme_key,
            "theme": THEMES[theme_key],
            "available_themes": list(THEMES.keys()),
        }

    elif res_type == "library":
        lib_key = ident.lower() if ident else "architecture"
        if lib_key not in LIBRARIES:
            # Check user libraries directory safely without allowing path traversal
            lib_dir = (Path(scene_directory()) / "libraries").resolve()
            try:
                user_lib_path = (lib_dir / f"{lib_key}.json").resolve()
                is_safe = user_lib_path.is_relative_to(lib_dir)
            except Exception:
                is_safe = False

            if not is_safe:
                raise SceneError(f"Library identifier '{ident}' is outside permitted directory")

            if user_lib_path.is_file():
                try:
                    data = json.loads(user_lib_path.read_text(encoding="utf-8"))
                    return {
                        "resource_type": "library",
                        "identifier": lib_key,
                        "library": data,
                        "source": "user_filesystem",
                    }
                except Exception as err:
                    raise SceneError(f"Failed to read custom library '{lib_key}': {err}") from err
            raise SceneError(
                f"Library '{lib_key}' not found. Available libraries: {list(LIBRARIES.keys())}"
            )
        return {
            "resource_type": "library",
            "identifier": lib_key,
            "library": LIBRARIES[lib_key],
            "available_libraries": list(LIBRARIES.keys()),
        }

    elif res_type == "element":
        if not ident:
            raise SceneError("Element ID is required for element resource retrieval")
        doc, rev = service.state.snapshot()
        index = {el["id"]: el for el in doc.get("elements", []) if not el.get("isDeleted")}
        if ident not in index:
            raise SceneError(f"Element '{ident}' not found in active scene")
        el = index[ident]
        # Collect bound label, frame, group peers, and connectors
        label = next(
            (lbl for lbl in index.values() if lbl.get("containerId") == ident),
            None,
        )
        frame = index.get(el.get("frameId")) if el.get("frameId") else None
        connected_arrows = [
            arr
            for arr in index.values()
            if arr.get("type") == "arrow"
            and any(
                (arr.get(end) or {}).get("elementId") == ident
                for end in ("startBinding", "endBinding")
            )
        ]
        group_peers = [
            peer["id"]
            for peer in index.values()
            if peer["id"] != ident
            and any(g in el.get("groupIds", []) for g in peer.get("groupIds", []))
        ]
        return {
            "resource_type": "element",
            "identifier": ident,
            "element": el,
            "label": label,
            "frame": frame,
            "connected_arrows": connected_arrows,
            "group_peers": group_peers,
            "revision": rev,
        }

    elif res_type == "capabilities":
        from .config import scene_directory, max_elements, configured_toolset
        toolset = configured_toolset()
        is_full = toolset == "full"
        return {
            "resource_type": "capabilities",
            "identifier": "capabilities",
            "active_toolset": toolset,
            "server_version": "0.2.0",
            "tool_count": 48 if is_full else 27,
            "config": {
                "scene_dir": str(scene_directory()),
                "max_elements": max_elements(),
            },
        }

    else:
        raise SceneError(
            f"Unsupported resource type '{res_type}'. Supported types: scene, library, theme, element, capabilities"
        )
