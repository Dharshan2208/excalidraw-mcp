---
name: flowcharts-and-processes
description: Design clear, human-polished flowcharts, decision trees, CI/CD pipelines, and state machines with single starts, clear terminals, labeled decision branches, and clean loop routing.
---

# Flowcharts and Processes

This skill guides the construction of readable, professional process diagrams and decision flows in Excalidraw. It eliminates messy spaghetti arrows, unlabeled branches, ambiguous decisions, and floating terminals.

---

## 1. Core Principles of Human-Quality Flowcharts

1. **Exactly One Start Node**: Every flowchart begins at a single entry point. Use a pill-shaped rectangle (`roundness: "round"`) with an inviting soft green tint (`#e6fcf5`, stroke `#0ca678`).
2. **Distinct Terminals**: Never leave an execution branch hanging. End every path with a terminal shape:
   - **Success / Completed**: Green tint (`backgroundColor: "#ebfbee"`, `strokeColor: "#2b8a3e"`).
   - **Failure / Abort / Quarantined**: Soft red tint (`backgroundColor: "#fff5f5"`, `strokeColor: "#c92a2a"`).
3. **Diamonds Strictly for Decisions**: Only use `add_diamond` for true conditional branching.
   - Text must be an explicit question ending with a question mark (e.g., `"Auth Valid?"`, `"Cache Hit?"`).
   - Every exiting connector MUST have an explicit label (`"Yes"`, `"No"`, `"Retry"`, `"Timeout"`).
   - Size diamonds at least `180px` wide and `110px` high to ensure inscribed labels do not clip corners.
4. **Consistent Primary Flow Direction**:
   - Default to **Top-to-Bottom (TB)** for business logic, algorithms, and decision trees.
   - Default to **Left-to-Right (LR)** for CI/CD pipelines, lifecycle stages, and multi-team handoffs.
   - Never reverse the primary direction for mainline progress.
5. **Clean Loop & Retry Routing**:
   - Backward loops (retries, polls) must route around the exterior perimeter, never cutting straight through intervening nodes.
   - Keep a minimum lateral clearance of `60px` from the main trunk corridor.
6. **Elbowed Connectors**: Always set `elbowed=True` on `connect` tool calls to produce neat, 90-degree orthogonal paths.

---

## 2. Decision Tree & Tool Selection

When rendering a flowchart or process:

```
Is it a standard linear flow or simple pipeline (< 8 nodes, no complex styling needed)?
  ├── YES -> Use `draw_mermaid` with direction TD or LR
  │          Example: graph TD; Start([Start]) --> Check{Valid?}; Check -- Yes --> Done([Done]); Check -- No --> Fail([Fail])
  └── NO  -> Use primitive tools (`add_rectangle`, `add_diamond`, `connect`)
             Provides exact coordinate control, custom semantic colors, bound labels, and perimeter loop routing.
```

*See [flowchart-patterns.md](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/flowcharts-and-processes/references/flowchart-patterns.md) for full layout dimensions and geometry templates.*

---

## 3. Step-by-Step Execution Workflow

### Step 1: Map Nodes and Coordinates
Before calling tools, calculate bounding boxes:
- **Trunk alignment**: Center all mainline steps along an axis (e.g., $X_{\text{center}} = 400$).
- **Standard step**: Width `200px`, Height `60px` $\rightarrow$ `x = 300`.
- **Diamond step**: Width `200px`, Height `110px` $\rightarrow$ `x = 300`.
- **Vertical pitch**: Advance `120px` to `150px` between consecutive step centers.
- **Branch offsets**: Place side branches at least `100px` away from the diamond edge ($X_{\text{branch}} \ge 580$).

### Step 2: Render Shapes
1. Create the single Start node (`add_rectangle`, `roundness: "round"`).
2. Create intermediate operation steps (`add_rectangle`, `roundness: "adaptive"`).
3. Create decision points (`add_diamond`, `roughness: 1`).
4. Create explicit terminal nodes for all outcomes.

### Step 3: Connect Shapes with Labels
1. Always use `connect(source_id, target_id)` which establishes automatic bound arrow endpoints.
2. Set `elbowed=True` for clean orthogonal bends.
3. Add explicit `label` arguments for all decision branches:
   ```python
   call_mcp_tool(
       "excalidraw",
       "connect",
       {
           "source_id": diamond_id,
           "target_id": success_step_id,
           "label": "Yes",
           "elbowed": True,
       },
   )
   ```

### Step 4: Route Retry Loops Around Trunk
For loops returning to an earlier stage:
- If using `connect`, route via an intermediary invisible anchor or position the retry step in a dedicated side gutter column.
- Verify connector paths do not intersect with text boxes.

---

## 4. Common Failures & Fixes

| Failure Mode | Visual Defect | Immediate Correction |
| :--- | :--- | :--- |
| **Orphaned Branch** | Flow path stops abruptly at an action with no terminal. | Add an explicit end terminal (`"Completed"`, `"Cancelled"`, or `"Escalated"`). |
| **Unlabeled Diamond Outlets** | Arrows leave a diamond without indicating which path is Yes or No. | Inspect `connect` calls and specify `label="Yes"` and `label="No"`. |
| **Text Clipping in Diamonds** | Question text overflows diamond apex corners. | Expand diamond dimensions to at least `200x120px` or shorten text to 3-4 keywords. |
| **Diagonal Arrow Clutter** | Straight diagonal arrows crossing through other boxes. | Enforce `elbowed=True` on all `connect` calls. |
| **Loop Slicing Trunk Nodes** | Retry arrow cuts through boxes between step 5 and step 2. | Place retry buffer node in a side lane ($X \ge 600$) and connect via the lane. |

---

## 5. Workflow Integration

- **Previous Stage**: Use [diagram-planning](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/diagram-planning/SKILL.md) to define branching logic, node counts, and flow direction.
- **Next Stage**: Proceed to [human-style-and-polish](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/human-style-and-polish/SKILL.md) to refine typography, corner rounding, and hand-drawn strokes.
- **Final Stage**: Conclude with [verify-and-editable-handoff](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/verify-and-editable-handoff/SKILL.md) to run geometry diagnostics and verify visual layout via PNG preview.
