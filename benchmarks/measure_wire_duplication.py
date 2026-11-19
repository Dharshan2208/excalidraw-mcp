"""Standalone reproducible benchmark to measure JSON-RPC wire duplication.

Measures the exact wire bytes and token consumption of FastMCP's tool response
payload under the current baseline (content + structuredContent) versus the
proposed single TextContent payload.
"""

import asyncio
import json
import sys

try:
    import tiktoken

    enc_o200k = tiktoken.get_encoding("o200k_base")
    enc_cl100k = tiktoken.get_encoding("cl100k_base")
except ImportError:
    print(
        "ERROR: tiktoken is required. Run with:\n"
        "  uv run --with tiktoken python benchmarks/measure_wire_duplication.py",
        file=sys.stderr,
    )
    sys.exit(1)

from excalidraw_mcp.server import create_server
from mcp.types import CallToolResult, TextContent


def count_tokens(text: str) -> dict[str, int]:
    return {
        "o200k": len(enc_o200k.encode(text)),
        "cl100k": len(enc_cl100k.encode(text)),
    }


async def main() -> None:
    server = create_server(toolset="core")
    # Call add_rectangle on baseline server
    res_before = await server.call_tool(
        "add_rectangle",
        {"x": 10, "y": 20, "w": 100, "h": 50, "label": "Box"},
    )

    # 1. Baseline wire representation
    content_blocks_before, struct_dict_before = res_before.to_mcp_result()
    wire_result_before = CallToolResult(
        content=content_blocks_before,
        structuredContent=struct_dict_before,
    )

    jsonrpc_before = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": wire_result_before.model_dump(
            by_alias=True, exclude_none=True
        ),
    }

    raw_jsonrpc_before = json.dumps(jsonrpc_before, separators=(",", ":"))
    content_json_before = json.dumps(
        [
            b.model_dump(by_alias=True, exclude_none=True)
            for b in content_blocks_before
        ],
        separators=(",", ":"),
    )
    struct_json_before = json.dumps(struct_dict_before, separators=(",", ":"))

    bytes_total_before = len(raw_jsonrpc_before.encode("utf-8"))
    bytes_content_before = len(content_json_before.encode("utf-8"))
    bytes_struct_before = len(struct_json_before.encode("utf-8"))
    tok_total_before = count_tokens(raw_jsonrpc_before)

    # 2. Proposed slimmed wire representation (pure ToolResult, no structuredContent)
    rect_id = struct_dict_before.get("rectangle_id")
    label_id = struct_dict_before.get("label_id")
    clean_text = json.dumps(
        {"rectangle_id": rect_id, "label_id": label_id},
        separators=(",", ":"),
    )
    wire_result_after = CallToolResult(
        content=[TextContent(type="text", text=clean_text)]
    )

    jsonrpc_after = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": wire_result_after.model_dump(
            by_alias=True, exclude_none=True
        ),
    }

    raw_jsonrpc_after = json.dumps(jsonrpc_after, separators=(",", ":"))
    content_json_after = json.dumps(
        [{"type": "text", "text": clean_text}],
        separators=(",", ":"),
    )

    bytes_total_after = len(raw_jsonrpc_after.encode("utf-8"))
    bytes_content_after = len(content_json_after.encode("utf-8"))
    tok_total_after = count_tokens(raw_jsonrpc_after)

    delta_bytes = bytes_total_before - bytes_total_after
    pct_bytes = (delta_bytes / bytes_total_before) * 100
    delta_tok_o200k = tok_total_before["o200k"] - tok_total_after["o200k"]
    pct_tok_o200k = (delta_tok_o200k / tok_total_before["o200k"]) * 100

    print("=" * 68)
    print("MCP WIRE DUPLICATION BENCHMARK: add_rectangle response")
    print("=" * 68)
    print(f"\n[1] BASELINE WIRE (FastMCP default: content + structuredContent)")
    print(f"  - Content block JSON:     {bytes_content_before:>4} bytes")
    print(f"  - StructuredContent JSON: {bytes_struct_before:>4} bytes")
    print(f"  - Full JSON-RPC Envelope: {bytes_total_before:>4} bytes")
    print(
        f"  - Tokens (o200k_base):     {tok_total_before['o200k']:>4} tokens"
    )
    print(
        f"  - Tokens (cl100k_base):    {tok_total_before['cl100k']:>4} tokens"
    )
    print(f"  - Payload:\n    {raw_jsonrpc_before}")

    print(
        f"\n[2] PROPOSED WIRE (ToolResult with clean content, structuredContent omitted)"
    )
    print(f"  - Content block JSON:     {bytes_content_after:>4} bytes")
    print(f"  - StructuredContent JSON:    0 bytes (omitted)")
    print(f"  - Full JSON-RPC Envelope: {bytes_total_after:>4} bytes")
    print(
        f"  - Tokens (o200k_base):     {tok_total_after['o200k']:>4} tokens"
    )
    print(
        f"  - Tokens (cl100k_base):    {tok_total_after['cl100k']:>4} tokens"
    )
    print(f"  - Payload:\n    {raw_jsonrpc_after}")

    print("\n[3] NET SAVINGS")
    print(
        f"  - Wire bytes:  {bytes_total_before}B -> {bytes_total_after}B "
        f"(-{delta_bytes}B, -{pct_bytes:.1f}%)"
    )
    print(
        f"  - Wire tokens: {tok_total_before['o200k']} -> {tok_total_after['o200k']} "
        f"(-{delta_tok_o200k} tok, -{pct_tok_o200k:.1f}%)"
    )
    print("=" * 68)


if __name__ == "__main__":
    asyncio.run(main())
