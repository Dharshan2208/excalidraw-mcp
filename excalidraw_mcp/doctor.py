"""Diagnostic runner for Excalidraw MCP server.

Performs sub-second verification of Python runtime, required dependencies,
bundled TrueType fonts, storage directory permissions, and agent skills.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from excalidraw_mcp.config import scene_directory


def check_python_version() -> dict[str, Any]:
    """Verify Python runtime meets >= 3.12 requirement."""
    major, minor, micro = sys.version_info[:3]
    ok = (major, minor) >= (3, 12)
    return {
        "name": "Python Runtime",
        "passed": ok,
        "detail": f"Python {major}.{minor}.{micro} (>= 3.12 required)",
    }


def check_dependencies() -> dict[str, Any]:
    """Verify presence of core runtime dependencies."""
    required = [
        "fastmcp",
        "pillow",
        "pygments",
        "cryptography",
        "starlette",
        "uvicorn",
        "pydantic",
        "mcp",
    ]
    installed: dict[str, str] = {}
    missing: list[str] = []

    for pkg in required:
        try:
            import importlib.metadata

            ver = importlib.metadata.version(pkg)
            installed[pkg] = ver
        except Exception:
            missing.append(pkg)

    ok = len(missing) == 0
    detail = (
        f"All {len(required)} dependencies installed ({', '.join(f'{k}=={v}' for k, v in installed.items())})"
        if ok
        else f"Missing dependencies: {', '.join(missing)}"
    )
    return {
        "name": "Dependencies",
        "passed": ok,
        "detail": detail,
        "installed": installed,
        "missing": missing,
    }


def check_font_engine() -> dict[str, Any]:
    """Verify TrueType font metrics and font discovery."""
    from excalidraw_mcp.fonts import list_fonts

    fonts = list_fonts()
    has_fonts = len(fonts) > 0
    font_names = [f.get("family", "") for f in fonts if f.get("family")]
    preview_names = sorted(font_names)[:5]
    return {
        "name": "Font Engine",
        "passed": has_fonts,
        "detail": f"Discovered {len(fonts)} available fonts ({', '.join(preview_names)})",
        "fonts": font_names,
    }


def check_scene_storage() -> dict[str, Any]:
    """Verify scene directory exists and is writable."""
    storage_dir = Path(scene_directory()).resolve()
    writable = False
    try:
        storage_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=storage_dir, delete=True) as f:
            f.write(b"probe")
            f.flush()
        writable = True
    except Exception as exc:
        writable = False
        detail = f"Directory {storage_dir} unwritable: {exc}"

    if writable:
        detail = f"Scene directory writable ({storage_dir})"

    return {
        "name": "Scene Storage",
        "passed": writable,
        "detail": detail,
        "path": str(storage_dir),
    }


def check_skills_package() -> dict[str, Any]:
    """Verify packaged agent skills are available and loadable."""
    from excalidraw_mcp.skills import list_skills

    skills = list_skills()
    ok = len(skills) >= 6
    detail = f"{len(skills)} agent skills discovered ({', '.join(sorted(skills))})"
    return {
        "name": "Agent Skills",
        "passed": ok,
        "detail": detail,
        "count": len(skills),
        "skills": sorted(skills),
    }


def run_diagnostics() -> dict[str, Any]:
    """Run all diagnostic probes and return structured results."""
    from excalidraw_mcp.server import get_server_version

    checks = [
        check_python_version(),
        check_dependencies(),
        check_font_engine(),
        check_scene_storage(),
        check_skills_package(),
    ]
    all_ok = all(c["passed"] for c in checks)
    return {
        "version": get_server_version(),
        "all_passed": all_ok,
        "checks": checks,
    }


def run_doctor_cli(argv: list[str]) -> int:
    """CLI handler for `exca-mcp doctor`."""
    parser = argparse.ArgumentParser(
        prog="exca-mcp doctor",
        description="Run non-destructive diagnostics on Excalidraw MCP runtime, fonts, and storage.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output diagnostics in JSON format",
    )
    args = parser.parse_args(argv)

    diag = run_diagnostics()

    if args.json:
        print(json.dumps(diag, indent=2))
        return 0 if diag["all_passed"] else 1

    print(f"Excalidraw MCP Doctor (v{diag['version']})")
    print("=" * 50)
    for c in diag["checks"]:
        status = "[PASS]" if c["passed"] else "[FAIL]"
        print(f"{status} {c['name']}: {c['detail']}")

    print("=" * 50)
    if diag["all_passed"]:
        print("All diagnostic checks passed. Server is ready.")
        return 0
    else:
        print("Some diagnostic checks failed. Please address issues above.", file=sys.stderr)
        return 1
