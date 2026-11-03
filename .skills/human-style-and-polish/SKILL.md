---
name: human-style-and-polish
description: Apply the professional hand-drawn Excalidraw aesthetic using restrained semantic palettes, intentional typography, consistent grid spacing, and verified geometric clearances.
---

# Human Style & Polish

This skill turns raw boxes and arrows into a clean, human-crafted Excalidraw diagram that looks like it was drawn by a seasoned software architect rather than an automated script.

---

## 1. The Hand-Drawn Excalidraw Aesthetic

Excalidraw’s visual charm and readability come from subtle organic line variance, not rigid geometry or messy sketches.

### Verified Style Parameters in Code
Every primitive shape tool (`add_rectangle`, `add_diamond`, `add_circle`) accepts these verified style parameters:

- **`roughness` (Integer: `0`, `1`, `2`)**:
  - `0`: Crisp, straight-line architectural blueprint style. Best for formal system documentation.
  - `1` (Recommended Default): Organic hand-drawn feel. Balances human character with clean technical precision.
  - `2`: Sketchy, ideation, informal brainstorming feel. Use sparingly for draft proposals.
- **`fillStyle` (`"solid"`, `"hachure"`, `"cross-hatch"`, `"zigzag"`)**:
  - `"solid"` (Default): High readability, crisp background contrast.
  - `"hachure"`: Angled sketch hatch lines. Excellent for external boundaries or untrusted zones.
  - `"cross-hatch"`: Dense woven hatch. Use for emphasized warning blocks or legacy legacy systems.
- **`strokeStyle` (`"solid"`, `"dashed"`, `"dotted"`)**:
  - `"solid"`: Active, direct synchronous links or solid service boundaries.
  - `"dashed"`: Asynchronous events, message queues, and optional/fallback paths.
  - `"dotted"`: Network security boundaries, audit logging, and telemetry streams.
- **`roundness` (`"adaptive"`, `"round"`, `"sharp"`)**:
  - `"adaptive"` (Default): Soft, professional rounded corners proportional to size.
  - `"round"`: Full pill shapes for client apps, terminals, and start/end tokens.
  - `"sharp"`: Square corners for databases, hard storage volumes, and external APIs.
- **`fontFamily` (`"excalifont"`, `"sans-serif"`, `"monospace"`, `"comic-shanns"`)**:
  - `"excalifont"` (Font 1): Standard Excalidraw handwritten font for natural, friendly diagrams.
  - `"sans-serif"` (Font 2): Clean, neutral typography for formal corporate presentations.
  - `"monospace"` (Font 3): Essential for endpoints (`/v1/orders`), SQL, topics, and environment variables.

---

## 2. Restrained Semantic Palettes (The 60-30-10 Rule)

Avoid "rainbow clown diagrams" where every box has an arbitrary color. Professional diagrams use at most 2–4 functional colors paired with clean neutrals:

- **60% Dominant Neutrals**:
  - Backgrounds: Canvas white `#ffffff` or soft cool gray `#f8f9fa`.
  - Node borders: Medium slate `#495057` or gray `#ced4da`.
  - Text: Dark charcoal `#212529` (never harsh 100% black `#000000`).
- **30% Structural Primary**:
  - One core color establishing the system boundary and primary services (e.g., Soft Blue `#e7f5ff` fill with `#1971c2` stroke).
- **10% Intentional Functional Accents**:
  - **Data Storage**: Soft Mint `#e6fcf5` fill, `#0ca678` stroke.
  - **Queues / Event Streams**: Soft Amber `#fff9db` fill, `#f59f00` stroke.
  - **External / Warning / Untrusted**: Soft Coral `#fff5f5` fill, `#e03131` stroke.

*Reference the complete palette definitions in [palette-catalog.md](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/human-style-and-polish/references/palette-catalog.md).*

---

## 3. Verified Spacing & Clearances

The Excalidraw MCP layout and routing engine operates on strict geometric rules. Respecting these numbers ensures automated verification passes cleanly:

| Parameter | Verified Source Value | Application Rule |
| :--- | :--- | :--- |
| **Obstacle Clearance** | `15.0px` (`routing.py`) | Connectors will avoid boxes by at least 15px. Keep all shapes at least 30px apart so connector corridors remain open. |
| **Parallel Lane Spacing** | `24.0px` (`routing.py`) | Multi-edge paths running side-by-side maintain a 24px gap. |
| **Default Node Gap** | `30.0px` (`auto_fix.py`) | Enforce at least 30px horizontal and vertical separation between sibling nodes. |
| **Spacing Violation Trigger** | `19.5px` (`0.65 * 30px`) | Any gap narrower than 19.5px triggers an automatic layout defect. |
| **Frame Internal Padding** | $\ge 40.0\text{px}$ | Child elements must sit at least 40px away from the boundary frame edge, and 50px below the frame header. |

---

## 4. Typography Hierarchy

Establish clear visual rank using standard sizing:

1. **Diagram Title**:
   - Size: `28px` bold
   - Placement: Top-left `(x=40, y=40)` or centered over canvas
   - Color: `#212529`
2. **Frame / Section Header**:
   - Size: `20px` bold or semi-bold
   - Placement: Inside boundary top-left `(x_frame + 20, y_frame + 20)`
   - Color: `#495057`
3. **Primary Node Label**:
   - Size: `16px` regular / medium
   - Position: Centered inside shape
   - Color: `#212529`
4. **Secondary Annotations / Protocols**:
   - Size: `12px` or `14px` monospace
   - Placement: Connector labels or subtext under primary node title
   - Color: `#868e96`

---

## 5. Machine-Generated Anti-Patterns Checklist

Before exporting or handing off a diagram, verify that none of these common defects are present:

- [ ] **No arbitrary rainbow coloring**: Every color serves a documented semantic purpose.
- [ ] **No uniform square sizing**: Component sizes reflect their purpose (e.g., small pills for clients, wide rectangles for services, diamonds for decisions).
- [ ] **No boundary breaches**: No child elements touch or overflow their parent frame border.
- [ ] **No intersecting connectors**: Connectors route orthogonally with `elbowed=True` and maintain `15px` clearance from node bodies.
- [ ] **No illegible micro-text**: All labels are $\ge 14\text{px}$ ($\ge 12\text{px}$ for secondary badges).
- [ ] **No floating unlabeled arrows**: All key paths have short protocol/action labels (`HTTP`, `gRPC`, `Kafka`, `SQL`).

*Review the detailed breakdown in [anti-patterns.md](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/human-style-and-polish/references/anti-patterns.md).*

---

## 6. Chaining

- **Upstream Skills**: Built upon layouts from [architecture-diagrams](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/architecture-diagrams/SKILL.md) or [flowcharts-and-processes](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/flowcharts-and-processes/SKILL.md).
- **Downstream Skill**: Proceed immediately to [verify-and-editable-handoff](file:///home/chifuyu/Coding/Self/Projects/excalidraw-mcp/.skills/verify-and-editable-handoff/SKILL.md) to run geometry diagnostics, verify visual quality via PNG preview, and save the editable `.excalidraw` file.
