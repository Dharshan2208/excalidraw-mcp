# Flowchart & Process Patterns Reference

This reference catalog provides concrete structural layouts, geometry calculations, and tool call templates for business processes, decision logic, event pipelines, and state machines.

---

## 1. Flowchart Topology Rules

### Single Start & Clear Terminals
- Every flowchart must have **exactly one** clear entry point (`add_rectangle` or `add_circle` styled as pill/rounded with green tint).
- Terminals (endpoints) must be differentiated:
  - **Success terminal**: Mint / soft green (`backgroundColor: "#ebfbee"`, `strokeColor: "#2b8a3e"`).
  - **Failure / Abort terminal**: Light salmon / soft red (`backgroundColor: "#fff5f5"`, `strokeColor: "#c92a2a"`).
  - **Terminal Dimensions**: W: 160-180px, H: 45-50px.

### Decision Nodes (`add_diamond`)
- **Strictly for binary or ternary conditional branching**. Never place long paragraphs or multi-step procedures inside a diamond.
- Text must be phrased as an explicit question ending in `?` (e.g., `"Valid Token?"`, `"Cache Hit?"`, `"Retry Count < 3?"`).
- **Dimensions**: Diamonds need larger bounding boxes to fit inscribed text without clipping:
  - Minimum width: `180px`, height: `110px`.
  - For 2-line questions: width: `200px`, height: `120px`.
- **Branch Connector Labels**: Every exiting connector from a diamond MUST have an explicit label:
  - Binary: `label="Yes"`, `label="No"`.
  - Conditional: `label="Success"`, `label="Timeout"`, `label="Failure"`.
  - Position: Always set `elbowed=True`.

---

## 2. Geometry Grid & Loop Routing

### Linear Vertical Flow (Top-to-Bottom)
- Standard step box: `width=200`, `height=60`.
- Vertical pitch (center-to-center): `120px` to `140px` (giving `60px` to `80px` vertical clearance between boxes).
- Center alignment: All primary trunk nodes share the same horizontal center:
  ```
  X_center = 400
  Box width = 200 => x = X_center - width/2 = 300
  ```

### Branching Horizontal Spacing
- Primary "Yes" branch continues down (trunk).
- "No" or "Alternative" branch exits right:
  - Diamond at `(x=300, y=240, w=200, h=120)` (center: 400, 300).
  - Alternative step placed at `x = 600`, `y = 270`, `w = 200`, `h = 60`.
  - Horizontal gap: `600 - (300 + 200) = 100px` (exceeds verified minimum clearance of 15px).

### Loop-Back & Retry Routing
To prevent backward arrows from cutting through intermediary nodes:
1. Route the connector via distinct elbow waypoints or place retry buffer nodes outside the trunk corridor.
2. Maintain at least 60px clearance from the side edges of intermediate trunk nodes.
3. Example: Trunk boxes span `x: 300..500`. Route the return path through `x = 180` or `x = 620`.

```
        +---------------+
        |  Start / Init |
        +-------+-------+
                |
                v
        +---------------+
+-----> | Process Event |
|       +-------+-------+
|               |
|               v
|       /---------------\       No
|      <  Valid Record?  > ------------> +---------------+
|       \-------+-------/                 | Quarantined   |
|               | Yes                     +---------------+
|               v
|       +---------------+
|       | Commit to DB  |
|       +-------+-------+
|               |
|               v
|       /---------------\       Yes
|      <   More Pages?   > ---------------+
|       \-------+-------/                 |
|               | No                      |
|               v                         |
|       +---------------+                 |
|       | Complete / End|                 |
|       +---------------+                 |
+-----------------------------------------+
```

---

## 3. Real Tool Execution Examples

### Pattern A: Primitive Flowchart (Start -> Decision -> Success / Retry Loop)

```python
# 1. Start Node (Pill shape)
call_mcp_tool(
    "excalidraw",
    "add_rectangle",
    {
        "x": 300,
        "y": 60,
        "w": 180,
        "h": 50,
        "label": "Start Job",
        "backgroundColor": "#e6fcf5",
        "strokeColor": "#0ca678",
        "roundness": "round",
        "roughness": 1,
    },
)

# 2. Ingest Step
call_mcp_tool(
    "excalidraw",
    "add_rectangle",
    {
        "x": 290,
        "y": 170,
        "w": 200,
        "h": 60,
        "label": "Read Next Batch",
        "backgroundColor": "#f8f9fa",
        "strokeColor": "#495057",
        "roundness": "adaptive",
        "roughness": 1,
    },
)

# 3. Decision Diamond
call_mcp_tool(
    "excalidraw",
    "add_diamond",
    {
        "x": 290,
        "y": 290,
        "w": 200,
        "h": 110,
        "label": "Payload Valid?",
        "backgroundColor": "#fff9db",
        "strokeColor": "#f59f00",
        "roughness": 1,
    },
)

# 4. Processing Step (Yes path)
call_mcp_tool(
    "excalidraw",
    "add_rectangle",
    {
        "x": 290,
        "y": 470,
        "w": 200,
        "h": 60,
        "label": "Transform & Ingest",
        "backgroundColor": "#e7f5ff",
        "strokeColor": "#1971c2",
        "roundness": "adaptive",
        "roughness": 1,
    },
)

# 5. Dead-Letter Step (No path)
call_mcp_tool(
    "excalidraw",
    "add_rectangle",
    {
        "x": 580,
        "y": 315,
        "w": 180,
        "h": 60,
        "label": "Send to DLQ",
        "backgroundColor": "#fff5f5",
        "strokeColor": "#fa5252",
        "roundness": "adaptive",
        "roughness": 1,
    },
)

# 6. Success End Node
call_mcp_tool(
    "excalidraw",
    "add_rectangle",
    {
        "x": 300,
        "y": 590,
        "w": 180,
        "h": 50,
        "label": "Job Finished",
        "backgroundColor": "#e6fcf5",
        "strokeColor": "#0ca678",
        "roundness": "round",
        "roughness": 1,
    },
)

# Connectors with bound endpoints and labels (connect automatically binds both ends)
call_mcp_tool(
    "excalidraw",
    "connect",
    {
        "source_id": "<start_id>",
        "target_id": "<read_id>",
        "elbowed": True,
    },
)

call_mcp_tool(
    "excalidraw",
    "connect",
    {
        "source_id": "<read_id>",
        "target_id": "<diamond_id>",
        "elbowed": True,
    },
)

call_mcp_tool(
    "excalidraw",
    "connect",
    {
        "source_id": "<diamond_id>",
        "target_id": "<process_id>",
        "label": "Yes",
        "elbowed": True,
    },
)

call_mcp_tool(
    "excalidraw",
    "connect",
    {
        "source_id": "<diamond_id>",
        "target_id": "<dlq_id>",
        "label": "No (Invalid)",
        "elbowed": True,
    },
)

call_mcp_tool(
    "excalidraw",
    "connect",
    {
        "source_id": "<process_id>",
        "target_id": "<end_id>",
        "elbowed": True,
    },
)
```

---

## 4. Mermaid vs Primitives Trade-Offs

| Criteria | `draw_mermaid` | Primitives (`add_rectangle`, `connect`) |
| :--- | :--- | :--- |
| **Best For** | Quick standard pipelines, documentation workflows, < 10 nodes | Custom semantic styling, human-polished looks, complex loops |
| **Styling Control** | Preset theme and stroke styles | Full granular control over colors, roughness, fonts, and roundness |
| **Branch Labels** | Supported via `A -- Yes --> B` syntax | Explicit binding via `connect(label="Yes", ...)` |
| **Editability** | Generated shapes are native Excalidraw elements | Elements fully bound with custom groupings |
| **Geometry Diagnostics**| Can be verified and adjusted with `auto_fix_layout` | Full verification and exact coordinate placement |
