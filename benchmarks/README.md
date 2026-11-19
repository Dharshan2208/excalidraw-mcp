# Reproducible Token & Schema Benchmarks

This directory contains standalone, reproducible benchmarking scripts for measuring MCP tool schemas, per-call responses, vision token costs, and end-to-end multi-turn scenario totals.

## Requirements & Environment

These benchmarks run using the project's standard `uv` tooling. Token calculations require `tiktoken` as an optional benchmark dependency. Do not add `tiktoken` to `pyproject.toml`; install it on-the-fly via `uv run`:

```bash
# Run the complete benchmark suite (Option B prototype, baseline, scenarios)
uv run --with tiktoken python benchmarks/token_benchmark.py

# Measure exact JSON-RPC wire byte and content/structuredContent duplication
uv run --with tiktoken python benchmarks/measure_wire_duplication.py

# Measure Option B prototype FastMCP server tools/list tokens
uv run --with tiktoken python benchmarks/prototype_option_b.py
```

If `tiktoken` is not installed, the scripts will exit with a clear, actionable error message.

## Tokenizer Details

- Primary Tokenizer: `tiktoken` with encoding `o200k_base` (OpenAI GPT-4o / GPT-4.5 standard).
- Secondary Tokenizer: `tiktoken` with encoding `cl100k_base` (OpenAI GPT-4 / Claude 3 token approximation).
- Note: Token counts are exact for these encodings and serve as close approximations (within ±5–10%) for client models using other tokenizers.
