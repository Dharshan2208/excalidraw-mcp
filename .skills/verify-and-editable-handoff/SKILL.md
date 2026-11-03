---
name: verify-and-editable-handoff
description: Run layout diagnostics, fix overlaps and spacing defects with auto_fix_layout, visually inspect PNG preview, enforce human editability, and export dual .excalidraw and PNG formats.
---

# Verify and Editable Handoff

This skill serves as the final quality gate and delivery mechanism for Excalidraw diagrams. It guarantees that generated diagrams are free of geometry bugs, visually balanced, and completely editable when opened by a human in [excalidraw.com](https://excalidraw.com).

---

## 1. Geometry Diagnostics & Automated Repair

Never hand off a diagram without verifying geometry. The MCP server provides built-in spatial diagnostics and rollback-safe repairs via `auto_fix_layout`.

### Step 1: Run Non-Mutating Diagnostics (`dry_run=True`)
Before modifying anything, inspect existing defects:

```python
result = call_mcp_tool(
    "excalidraw",
    "auto_fix_layout",
    {
        "dry_run": True,
        "repair_scope": "all",
        "min_gap": 30.0,
    },
)
# Inspect result["initial_issues"] and result["status"]:
# - status: "no_changes_needed" (or len(initial_issues) == 0) indicates clean geometry
# - initial_issues contains any detected defects:
#   * overlaps (box-over-box collisions)
#   * text_clipping (labels exceeding shape bounds)
#   * frame_escapes (children outside frame bounds)
#   * routing_collisions (connectors crossing shapes)
#   * spacing_violations (elements separated by < 19.5px)
```

### Step 2: Intentional Overlaps Handling
If certain elements intentionally overlap (e.g., a status badge overlapping a card corner or layered icon tiles), tag them with custom metadata so the diagnostic engine ignores them:
```json
{
  "customData": {
    "allow_overlap": true
  }
}
```

### Step 3: Apply Automated Repair
If actionable defects exist, run `auto_fix_layout` with repair mode:

```python
repair_result = call_mcp_tool(
    "excalidraw",
    "auto_fix_layout",
    {
        "dry_run": False,
        "repair_scope": "all",  # or "overlaps", "containment", "routing", "spacing"
        "aggressiveness": "balanced",  # "conservative", "balanced", or "aggressive"
        "min_gap": 30.0,
    },
)
```
*Note: `auto_fix_layout` provides rollback safety. If an aggressive repair produces an undesirable layout, invoke `undo` immediately to restore the previous canvas state.*

---

## 2. Visual Inspection via Preview

Do not assume a mathematically valid layout looks visually appealing. Always inspect the visual rendering:

1. Call the `preview` tool:
   ```python
   image_result = call_mcp_tool(
       "excalidraw",
       "preview",
       {
           "scale": 1.0,
           "padding": 40,
           "background": True,
       },
   )
   ```
2. Inspect the rendered image for:
   - Visual balance and whitespace distribution.
   - Flow clarity (no confusing zigzag arrow routes).
   - Label legibility (font sizes large enough at standard zoom).
   - Frame alignment and padding.

---

## 3. Human Editability Standards

A diagram is only successful if a human engineer can open it in Excalidraw and make adjustments without breaking the structure. Ensure these 4 rules are satisfied:

1. **Bound Connectors**:
   - All arrows must be created using the `connect(source_id, target_id)` tool, which automatically establishes bound start and end anchor bindings.
   - When a user clicks and drags a service or database node in Excalidraw, the attached connectors must follow automatically.
2. **Bound Labels**:
   - Always supply text labels directly through shape properties (`label` in `add_rectangle`, `add_diamond`) rather than loose floating text boxes positioned on top.
   - Bound labels center automatically when shapes resize.
3. **No Permanently Locked Elements**:
   - Ensure elements are not left locked (`locked: true`), allowing the user immediate manipulation.
4. **Logical Grouping / Frames**:
   - Group related subcomponents or place them inside frames (`add_frame`) so they can be selected and moved as a unit.

---

## 4. Exporting Dual Formats

Deliver diagrams in both high-resolution bitmap and native editable vector format.

### 1. High-Resolution PNG Export
Save a crisp bitmap for documentation, pull requests, or README files:
```python
call_mcp_tool(
    "excalidraw",
    "export_png",
    {
        "name": "system-architecture",
        "directory": "docs",  # or target directory
        "scale": 2.0,  # 2.0 provides retina-sharp rasterization
        "padding": 40,
        "background": True,
        "overwrite": True,
    },
)
```

### 2. Native Editable Excalidraw File
Save a native `.excalidraw` document snapshot:
```python
# Option A: Save directly to the scenes repository directory
call_mcp_tool(
    "excalidraw",
    "save",
    {
        "name": "system-architecture",
        "overwrite": True,
    },
)

# Option B: Export the raw JSON document to write to a project path
scene_export = call_mcp_tool("excalidraw", "export_scene", {})
# Returns EmbeddedResource containing scene JSON, which can be saved to docs/system-architecture.excalidraw
```

---

## 5. Verification Checklist

Run through the [delivery-checklist.md](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/verify-and-editable-handoff/references/delivery-checklist.md) before marking the task complete:

- [ ] `auto_fix_layout(dry_run=True)` reports status `"no_changes_needed"` (0 initial issues).
- [ ] Visual preview inspected and verified clean.
- [ ] All arrows have bound endpoints via `connect(source_id, target_id)`.
- [ ] All shape labels bound directly to host shapes.
- [ ] Dual export completed (`.png` and `.excalidraw`).

---

## 6. Chaining

This is the terminal skill in the Excalidraw pipeline:
1. [diagram-planning](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/diagram-planning/SKILL.md) $\rightarrow$ Scope, tiers, and layout selection.
2. [architecture-diagrams](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/architecture-diagrams/SKILL.md) or [flowcharts-and-processes](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/flowcharts-and-processes/SKILL.md) $\rightarrow$ Structural node placement.
3. [human-style-and-polish](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/human-style-and-polish/SKILL.md) $\rightarrow$ Aesthetic refinement and semantic palette.
4. **verify-and-editable-handoff** $\rightarrow$ Diagnostic verification, preview inspection, and delivery.
