"""Excalidraw MCP server package."""

from excalidraw_mcp.server import create_server, get_server_version, main, mcp, run

__version__ = get_server_version()

__all__ = ["__version__", "create_server", "get_server_version", "main", "mcp", "run"]
