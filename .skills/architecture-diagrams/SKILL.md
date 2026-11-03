---
name: architecture-diagrams
description: Design and implement production-grade system, cloud, distributed services, and infrastructure architecture diagrams using the exca-mcp MCP server. Use when creating multi-tier backend architectures, microservices topologies, cloud infrastructure, trust and deployment boundaries, or database persistence diagrams with frames, side columns, and explicit protocol connectors.
---

# Architecture Diagrams — Multi-Tier System Design

## Overview
Architectural diagrams model real-world production systems: client tiers, API gateways, microservices, databases, caches, queues, and external cloud integrations. This skill provides the exact procedural rules, spatial coordinates, component shapes, and MCP tool invocations to construct human-crafted architecture diagrams.

---

## 1. Architectural Tiering Standards

Arrange system components in strict logical tiers (Top-to-Bottom or Left-to-Right). Never intermingle presentation with persistence:

1. **Tier 1 — Clients & Edge**: Web SPAs, mobile apps, CLI runners, IoT endpoints.
2. **Tier 2 — Ingress & Security Gateway**: Reverse proxies (Envoy/Nginx), API gateways (Kong), load balancers (ALB), WAF.
3. **Tier 3 — Application Services**: Microservices, domain workers, asynchronous event consumers.
4. **Tier 4 — Persistence & State**: Relational databases (PostgreSQL), distributed caches (Redis), document stores, event logs (Kafka).
5. **Tier 5 — External Systems**: Third-party APIs (Stripe, Twilio), external cloud backends, SaaS platforms.

---

## 2. Frames for Boundaries & Isolation

Use `add_frame` to represent physical and logical boundaries:
- **Trust Boundaries**: DMZ, private subnets, secure enclave.
- **Deployment Boundaries**: Kubernetes cluster, AWS VPC, Docker network.
- **Subsystem Domains**: Billing subsystem, User Identity domain.

```python
# Create a tier frame container (Width: 1560px, Height: 160px)
frame_result = await client.call_tool("add_frame", {
    "name": "Tier 3 — Application Services",
    "x": 100.0,
    "y": 520.0,
    "w": 1560.0,
    "h": 160.0,
})
frame_id = frame_result["frame_id"]
```

---

## 3. Shape & Styling Conventions

| Role | Tool | Stroke Color | Background Fill | Roughness | Roundness |
|---|---|---|---|---|---|
| Client / UI | `add_rectangle` | `#1971c2` | `#e7f5ff` | `1` | `"round"` |
| Gateway / Ingress | `add_rectangle` | `#0c8599` | `#e3fafc` | `1` | `"round"` |
| Core Service | `add_rectangle` | `#5f3dc4` | `#f3f0ff` | `1` | `"round"` |
| Database / Store | `add_rectangle` | `#2f9e44` | `#ebfbee` | `1` | `"round"` |
| Event / Queue | `add_rectangle` | `#d9480f` | `#fff4e6` | `1` | `"round"` |
| Security / Firewall | `add_rectangle` | `#c92a2a` | `#ffe3e3` | `1` | `"round"` |
| External 3rd Party | `add_rectangle` | `#495057` | `#f1f3f5` | `1` | `"sharp"` |

---

## 4. Why Primitives Outperform Shorthand

While `draw_architecture` is available for quick prototypes, **production diagrams must use Primitives (`add_frame`, `add_rectangle`, `connect`)**:
1. `draw_architecture` styles all elements identically and only supports a single horizontal grid.
2. Primitives allow per-tier framing, custom semantic colors per service, and exact coordinate snapping.
3. `connect(source_id, target_id)` establishes dynamic arrow bindings that anchor perpendicularly to cardinal faces.

---

## 5. Worked Example: 3-Tier Microservice Architecture

Copy-pasteable workflow using verified MCP tool calls:

```python
# 1. Clear working canvas
await client.call_tool("clear", {})

# 2. Add Diagram Title
await client.call_tool("add_text", {
    "content": "E-Commerce Core Platform — Production Architecture",
    "x": 100.0,
    "y": 40.0,
    "font_size": 24,
})

# 3. Add Tier 1 Frame (Clients)
t1_frame = await client.call_tool("add_frame", {
    "name": "Tier 1 — Presentation Layer",
    "x": 100.0, "y": 140.0, "w": 1200.0, "h": 130.0,
})

# 4. Add Tier 1 Component
client_box = await client.call_tool("add_rectangle", {
    "label": "Web Client\nNext.js SPA",
    "x": 160.0, "y": 175.0, "w": 240.0, "h": 70.0,
    "frame_id": t1_frame["frame_id"],
    "strokeColor": "#1971c2", "backgroundColor": "#e7f5ff",
    "fillStyle": "solid", "roundness": "round", "roughness": 1,
})

# 5. Add Tier 2 Frame (Gateway & Services)
t2_frame = await client.call_tool("add_frame", {
    "name": "Tier 2 — Ingress & Microservices",
    "x": 100.0, "y": 320.0, "w": 1200.0, "h": 140.0,
})

gateway_box = await client.call_tool("add_rectangle", {
    "label": "Kong API Gateway\nRate Limiting • JWT Auth",
    "x": 160.0, "y": 355.0, "w": 260.0, "h": 75.0,
    "frame_id": t2_frame["frame_id"],
    "strokeColor": "#0c8599", "backgroundColor": "#e3fafc",
    "fillStyle": "solid", "roundness": "round", "roughness": 1,
})

order_svc = await client.call_tool("add_rectangle", {
    "label": "Order Service\nGo • gRPC Engine",
    "x": 560.0, "y": 355.0, "w": 240.0, "h": 75.0,
    "frame_id": t2_frame["frame_id"],
    "strokeColor": "#5f3dc4", "backgroundColor": "#f3f0ff",
    "fillStyle": "solid", "roundness": "round", "roughness": 1,
})

# 6. Add Tier 3 Frame (Persistence)
t3_frame = await client.call_tool("add_frame", {
    "name": "Tier 3 — Storage & Caching",
    "x": 100.0, "y": 510.0, "w": 1200.0, "h": 140.0,
})

db_box = await client.call_tool("add_rectangle", {
    "label": "Orders Database\nPostgreSQL 16 HA Cluster",
    "x": 560.0, "y": 545.0, "w": 260.0, "h": 75.0,
    "frame_id": t3_frame["frame_id"],
    "strokeColor": "#2f9e44", "backgroundColor": "#ebfbee",
    "fillStyle": "solid", "roundness": "round", "roughness": 1,
})

# 7. Connect Components with Protocol Labels
await client.call_tool("connect", {
    "source_id": client_box["rectangle_id"],
    "target_id": gateway_box["rectangle_id"],
    "label": "HTTPS / TLS",
    "elbowed": True,
    "strokeStyle": "solid",
    "strokeColor": "#1e1e1e",
})

await client.call_tool("connect", {
    "source_id": gateway_box["rectangle_id"],
    "target_id": order_svc["rectangle_id"],
    "label": "gRPC RPC",
    "elbowed": True,
    "strokeStyle": "solid",
    "strokeColor": "#5f3dc4",
})

await client.call_tool("connect", {
    "source_id": order_svc["rectangle_id"],
    "target_id": db_box["rectangle_id"],
    "label": "SQL (Read/Write)",
    "elbowed": True,
    "strokeStyle": "solid",
    "strokeColor": "#2f9e44",
})
```

---

## 6. Connector Semantics

- **Synchronous RPC / HTTP**: `strokeStyle="solid"`, dark stroke `#1e1e1e` or tier color.
- **Asynchronous / Messaging / PubSub**: `strokeStyle="dashed"`, accent color `#d9480f`.
- **Database Connection / Storage**: `strokeStyle="solid"`, green `#2f9e44`.
- **Labels**: Always include concise protocol or active verbs (`"HTTPS"`, `"gRPC"`, `"Publishes event"`, `"SQL Query"`).

---

## Workflow Chaining
1. **Pre-requisite**: Load `diagram-planning` to define component counts, tiers, and palette.
2. **Active Step**: Construct architecture frames, components, and connections as documented above.
3. **Next Step**: Apply visual craftsmanship and grid spacing using `human-style-and-polish`.
4. **Final Step**: Validate geometry and generate output using `verify-and-editable-handoff`.

---

## Common Failures & Fixes

| Failure Pattern | Root Cause | Immediate Fix |
|---|---|---|
| Floating text drifting when shape is moved | Calling `add_text` on top of a rectangle instead of `label` | Pass `label="Title\nSubtitle"` directly into `add_rectangle` so text is permanently centered and bound |
| Frame child leaves frame on dragging | Creating shapes without `frame_id` | Always capture `frame_id` from `add_frame` and pass it to every child shape |
| Arrows cutting through service boxes | Using straight arrows diagonally across intermediate tiers | Set `elbowed=True` in `connect` so Manhattan A* routes along clear $15\text{px}$ corridors |
| Unbalanced box heights across a row | Guessing individual heights for each node | Set identical standard heights for peers in the same tier (e.g. `w=240.0, h=75.0`) |
