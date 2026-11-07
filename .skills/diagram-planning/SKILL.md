---
name: diagram-planning
description: Formulate a structured architectural plan before invoking any Excalidraw MCP creation tool. Use when an agent receives any diagram request (architecture, flowchart, data pipeline, system design) to determine diagram type, audience, layout tiers, flow direction, node density limits, entry tool selection, and semantic color palette before drawing.
---

# Diagram Planning — Pre-Drawing Architecture Plan

## Overview
Never invoke diagram tools without an upfront plan. Unplanned element creation causes wire crossing, overlapping containers, inconsistent spacing, and cognitive overload. This skill transforms a user prompt into a concrete 5-point execution plan.

---

## The 5-Step Planning Procedure

Follow these 5 steps sequentially before invoking any tool:

### 1. Identify Diagram Type & Target Audience
- **System / Software Architecture**: High-level component interactions, deployment tiers, microservices, cloud topologies. Target: Engineering leads, design review boards, system architects. $\rightarrow$ Chain to `architecture-diagrams`.
- **Flowchart / Process / Pipeline**: Conditional logic, decision trees, CI/CD pipelines, request lifecycles. Target: Developers, DevOps engineers, product managers. $\rightarrow$ Chain to `flowcharts-and-processes`.
- **Entity / Data Flow Diagram**: Data transformations, event propagation, message queues. $\rightarrow$ Chain to `architecture-diagrams`.

### 2. Enumerate Components & Relationships
- List all major components with their single-sentence responsibility and technology stack (e.g., `API Gateway (Kong / Envoy)`, `Order Service (Go / gRPC)`, `Primary DB (PostgreSQL 16)`).
- List all directional connections with protocol or verb (e.g., `Client -> Gateway via HTTPS`, `Gateway -> Service via gRPC`, `Service -> DB via SQL (read/write)`).
- Separate internal system components from external dependencies (third-party APIs, SaaS, legacy systems).

### 3. Establish Layout Structure & Flow Direction
- **Direction Rules**:
  - **Top-to-Bottom (TB)**: Hierarchical architectures, client-server tiering, and operational workflows.
  - **Left-to-Right (LR)**: Data processing pipelines, message streams, and time-sequential workflows.
- **Tier Boundaries**: Group components into 3 to 6 logical tiers:
  - Tier 1: Clients & Presentation Layer
  - Tier 2: Edge, API Gateway & Ingress
  - Tier 3: Core Services, Workers & Processing Engines
  - Tier 4: Storage, Databases & Caches
  - Tier 5: External Dependencies & 3rd-Party Integrations
- **Side Columns / Cross-Cutting Concerns**: Place persistent side concerns (Auth/IAM, Observability/Logging, Telemetry) in dedicated vertical side columns rather than cutting through core tiers.

### 4. Cap Density & Split Complex Diagrams
- **Strict Density Limit**: Cap primary diagrams at **12 to 16 core nodes** (maximum 20).
- **Split Rule**: If a system has $>16$ components, do not force them into a single congested canvas:
  1. Produce a **System Context Diagram (L1)** showing major subsystems and external boundaries.
  2. Produce focused **Subsystem Container Diagrams (L2)** for detailed internals.
- **Inter-node Spacing Baseline**: Budget $60\text{px}-100\text{px}$ horizontal gap and $40\text{px}-80\text{px}$ vertical gap between shapes.

### 5. Select Entry Tool & Palette
- **Tool Selection Decision**: See [Entry Tool Decision Tree](./references/entry-tool-decision-tree.md).
  - Use **Primitives (`add_rectangle`, `add_frame`, `connect`)** for production multi-tier architecture diagrams where each layer has distinct colors, frames, and precise docking.
  - Use **`draw_mermaid`** for fast flowcharts, state transitions, or sequence trees.
  - Use **`draw_architecture`** only for simple single-tier component lists ($<6$ items).
- **Semantic Palette Selection** (see `human-style-and-polish`):
  - Neutral canvas: Background `#ffffff`, text/borders `#1e1e1e`.
  - Blue (`#1971c2` stroke, `#e7f5ff` fill): Clients, UI, Frontend.
  - Cyan (`#0c8599` stroke, `#e3fafc` fill): Gateways, Load Balancers, Ingress.
  - Violet (`#5f3dc4` stroke, `#f3f0ff` fill): Backend Services, Microservices.
  - Green (`#2f9e44` stroke, `#ebfbee` fill): Databases, Storage, Persistence.
  - Orange (`#d9480f` stroke, `#fff4e6` fill): Queues, Event Streams, Workers.
  - Red (`#c92a2a` stroke, `#ffe3e3` fill): Security boundaries, Firewalls, Alerts.
  - Gray (`#495057` stroke, `#f1f3f5` fill): External third-party systems.

---

## Output of this Skill: The Planning Template

Before calling tools, write out the plan in this format:

```text
DIAGRAM EXECUTION PLAN
1. Title: [Title of Diagram]
2. Audience & Goal: [e.g. Design review of payment processing architecture]
3. Layout & Direction: [e.g. Top-to-Bottom, 5 Tiers + 1 Observability side column]
4. Component Roster (Count: [N <= 16]):
   - Tier 1: Web Client, Mobile App
   - Tier 2: Cloudflare CDN, Kong API Gateway
   - Tier 3: Auth Service, Checkout Service, Payment Worker
   - Tier 4: Redis Cache, PostgreSQL Cluster, Kafka Event Bus
   - Tier 5: Stripe API, Bank Gateway
   - Side Column: Prometheus & Datadog
5. Selected Tool: Primitives (add_frame + add_rectangle + connect)
6. Palette:
   - Clients: #1971c2 / #e7f5ff
   - Edge: #0c8599 / #e3fafc
   - Core: #5f3dc4 / #f3f0ff
   - Data/Queues: #2f9e44 / #ebfbee and #d9480f / #fff4e6
   - External: #495057 / #f1f3f5
```

---

## Workflow Chaining
- Once the plan is established, proceed to:
  - **`architecture-diagrams`** for multi-tier infrastructure, cloud, and backend systems.
  - **`flowcharts-and-processes`** for pipelines, business logic, and branching decisions.
- After layout generation, always apply **`human-style-and-polish`** and run **`verify-and-editable-handoff`**.

---

## Common Failures & Fixes

| Failure Pattern | Root Cause | Immediate Fix |
|---|---|---|
| Spider-web intersecting lines | Connecting nodes without grouping them into spatial tiers | Re-order components into monotonic tiers (Tier 1 $\rightarrow$ Tier 2 $\rightarrow$ Tier 3); avoid jumping tiers |
| Canvas crowding ($>25$ boxes) | Trying to cram whole company infrastructure into one view | Split into a high-level Context diagram and detailed Container diagrams |
| Text clipping container border | Guessing box width without accounting for font measurement | Use standard widths ($140\text{px}-180\text{px}$ for services, $200\text{px}-260\text{px}$ for multi-line labels); let `auto_fix_layout` expand if needed |
| Unaligned sibling nodes | Arbitrary $(x, y)$ coordinates across peer boxes | Use a fixed grid step (e.g. $X = 160, 560, 960$ for 3-column rows; common $Y$ for all peers in a tier) |
