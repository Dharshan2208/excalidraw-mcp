"""Client configuration generator for Excalidraw MCP server.

Emits clean, copy-pasteable JSON configuration snippets or CLI commands
for Claude Desktop, Claude Code, Cursor, Zed, Windsurf, OpenCode, and Antigravity.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

CLIENT_TEMPLATES: dict[str, Any] = {
    "claude-desktop": {
        "filename": "claude_desktop_config.json",
        "doc_url": "https://docs.anthropic.com/en/docs/agents-and-tools/mcp#claude-desktop",
        "config": {
            "mcpServers": {
                "excalidraw": {
                    "command": "uvx",
                    "args": ["exca-mcp"],
                }
            }
        },
    },
    "cursor": {
        "filename": ".cursor/mcp.json",
        "doc_url": "https://docs.cursor.com/context/model-context-protocol",
        "config": {
            "mcpServers": {
                "excalidraw": {
                    "command": "uvx",
                    "args": ["exca-mcp"],
                }
            }
        },
    },
    "windsurf": {
        "filename": "~/.codeium/windsurf/mcp_config.json",
        "doc_url": "https://codeium.com/windsurf",
        "config": {
            "mcpServers": {
                "excalidraw": {
                    "command": "uvx",
                    "args": ["exca-mcp"],
                }
            }
        },
    },
    "antigravity": {
        "filename": "~/.gemini/antigravity-cli/mcp_config.json",
        "doc_url": "https://github.com/Dharshan2208/excalidraw-mcp",
        "config": {
            "mcpServers": {
                "excalidraw": {
                    "command": "uvx",
                    "args": ["exca-mcp"],
                }
            }
        },
    },
    "zed": {
        "filename": "~/.config/zed/settings.json",
        "doc_url": "https://zed.dev/docs/assistant/model-context-protocol",
        "config": {
            "context_servers": {
                "excalidraw": {
                    "command": {
                        "path": "uvx",
                        "args": ["exca-mcp"],
                    }
                }
            }
        },
    },
    "opencode": {
        "filename": "~/.config/opencode/config.json",
        "doc_url": "https://opencode.ai",
        "config": {
            "mcp": {
                "excalidraw": {
                    "type": "local",
                    "command": ["uvx", "exca-mcp"],
                }
            }
        },
    },
}


def list_supported_clients() -> list[str]:
    """Return list of supported client names."""
    return sorted(list(CLIENT_TEMPLATES.keys()) + ["claude-code"])


def get_client_config(client: str, full: bool = False) -> str:
    """Return formatted configuration block or CLI command for specified client."""
    client_key = client.strip().lower()

    if client_key == "claude-code":
        env_flag = " -e EXCALIDRAW_TOOLSET=full" if full else ""
        return f"claude mcp add excalidraw{env_flag} uvx exca-mcp\n"

    if client_key not in CLIENT_TEMPLATES:
        supported = ", ".join(list_supported_clients())
        raise ValueError(f"Unknown client '{client}'. Supported clients: {supported}")

    tpl = CLIENT_TEMPLATES[client_key]
    cfg = json.loads(json.dumps(tpl["config"]))

    if full:
        if client_key in ("claude-desktop", "cursor", "windsurf", "antigravity"):
            cfg["mcpServers"]["excalidraw"]["env"] = {"EXCALIDRAW_TOOLSET": "full"}
        elif client_key == "zed":
            cfg["context_servers"]["excalidraw"]["command"]["env"] = {"EXCALIDRAW_TOOLSET": "full"}
        elif client_key == "opencode":
            cfg["mcp"]["excalidraw"]["environment"] = {"EXCALIDRAW_TOOLSET": "full"}

    header = f"// Configuration for {client_key} ({tpl['filename']})\n"
    return header + json.dumps(cfg, indent=2) + "\n"


def run_config_printer_cli(argv: list[str]) -> int:
    """CLI handler for `exca-mcp print-config`."""
    parser = argparse.ArgumentParser(
        prog="exca-mcp print-config",
        description="Print copy-pasteable MCP client configuration snippets.",
    )
    parser.add_argument(
        "client",
        nargs="?",
        default="claude-desktop",
        help=f"Target client: {', '.join(list_supported_clients())} (default: claude-desktop, or 'all')",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Include EXCALIDRAW_TOOLSET=full environment variable in configuration",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print raw JSON without comments or headers",
    )

    args = parser.parse_args(argv)

    if args.client == "all":
        for c in list_supported_clients():
            print(f"=== {c} ===")
            print(get_client_config(c, full=args.full))
        return 0

    try:
        output = get_client_config(args.client, full=args.full)
        if args.json and not args.client == "claude-code":
            # Strip comment header if --json is passed
            lines = output.splitlines()
            if lines and lines[0].startswith("//"):
                output = "\n".join(lines[1:]) + "\n"
        sys.stdout.write(output)
        sys.stdout.flush()
        return 0
    except ValueError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1
