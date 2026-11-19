# Structured Graph Generation

The `generate_diagram` tool (with `format="graph"`) replaces the current scene atomically with a structured Sugiyama layered graph:

```python
generate_diagram(
    format="graph",
    nodes=[
        {"id": "client", "label": "Client", "shape": "rectangle"},
        {"id": "api", "label": "API", "shape": "diamond"},
        {"id": "db", "label": "Database", "shape": "ellipse"},
        {"id": "cache", "label": "Cache", "shape": "rectangle"}
    ],
    edges=[
        {"id": "request", "source": "client", "target": "api", "label": "HTTP"},
        {"id": "persist", "source": "api", "target": "db"},
        {"id": "lookup", "source": "api", "target": "cache", "label": "read"}
    ],
    layout="layered",
    direction="horizontal"
)
```

Caller IDs are stable logical identifiers; the result's `node_map` and `edge_map` map them to generated Excalidraw element and label IDs.

---

## Layout Types & Direction

- **`layered`**: Assigns longest-path ranks and supports branches and isolated nodes. It requires an acyclic graph.
- **`horizontal` / `vertical`**: Places nodes linearly in input order and supports cyclic edge sets.

Layout computation is deterministic.

---

## Spacing & Geometrical Envelopes

- Spacing accumulates actual node dimensions, preventing fixed-gap overlap.
- Labels wrap at 24 characters, and dimensions dynamically account for line count and shape padding.
- Arrow endpoints use exact rectangle, diamond, or ellipse boundaries and account for imported shape rotation.
- Limits are 200 nodes, 500 edges, 2,000 characters per label, and 200 characters per logical ID.
- Node IDs and explicit edge IDs must be unique; endpoints must exist; self-loops are rejected. Invalid input and layout failures preserve the previous scene.
