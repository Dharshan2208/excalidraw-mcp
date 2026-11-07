# Contributing to Excalidraw MCP

Thank you for your interest in contributing to Excalidraw MCP (`exca-mcp`).

## Development Setup

### Prerequisites
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or `pip` / `virtualenv`

### Clone & Install
```bash
git clone https://github.com/Dharshan2208/excalidraw-mcp.git
cd excalidraw-mcp

# Create virtual environment and install dependencies
uv sync --all-extras
```

## Running Tests

Excalidraw MCP maintains comprehensive test coverage across all tools, services, serializers, routing, and packaging.

To run the test suite:

```bash
# Using unittest (as configured in CI)
uv run --locked python -B -m unittest discover -s tests -v

# Or using pytest
uv run pytest
```

### Static Analysis and Compilation
Verify that all Python sources compile cleanly without syntax errors:

```bash
python -m compileall excalidraw_mcp tests
```

### Build & Package Validation
Verify distribution packaging and metadata:

```bash
uv build
uvx twine check dist/*
```

## Pull Request Guidelines

1. **Verify Claims & Tools**: When modifying MCP tools or documentation, verify that tool signatures and parameter descriptions remain accurate.
2. **Keep Core Minimal**: The default `core` toolset is intentionally limited to essential tools for token efficiency. New tools should generally belong to the `full` toolset unless essential for standard workflows.
3. **No Regressions**: Ensure all existing tests pass before opening a PR.
4. **Security**: Ensure file paths and external inputs are validated.
