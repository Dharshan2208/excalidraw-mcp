# Software Architecture Design Patterns & Layout Geometry

## 1. Multi-Tier Grid Coordinate Architecture

Standard coordinates for a balanced 5-tier architecture canvas ($1600\text{px}$ width):

```
Y = 40    [Diagram Title & Subtitle]                          [Compact Legend] (X: 1100)
Y = 150   ┌── Frame: Tier 1 — Clients & Presentation (H: 140) ─────────────────────────┐
          │  Box 1 (X: 160)            Box 2 (X: 640)            Box 3 (X: 1140)       │
          └────────────────────────────────────────────────────────────────────────────┘
Y = 330   ┌── Frame: Tier 2 — Gateways & Ingress (H: 150) ─────────────────────────────┐
          │  Box 1 (X: 240)                      Box 2 (X: 900)                        │
          └────────────────────────────────────────────────────────────────────────────┘
Y = 520   ┌── Frame: Tier 3 — Application Services (H: 160) ───────────────────────────┐
          │  Service A (X: 160)   Service B (X: 600)   Service C (X: 1040)             │
          └────────────────────────────────────────────────────────────────────────────┘
Y = 720   ┌── Frame: Tier 4 — Data Persistence & Storage (H: 160) ─────────────────────┐
          │  Cache (X: 200)       Primary DB (X: 660)  Event Stream (X: 1120)          │
          └────────────────────────────────────────────────────────────────────────────┘
Y = 920   ┌── Frame: Tier 5 — External Integrations & Cloud (H: 150) ──────────────────┐
          │  3rd Party API (X: 300)                    Cloud Provider (X: 900)         │
          └────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Side Columns & Cross-Cutting Banners

When representing cross-cutting infrastructure (e.g. Identity/IAM, Observability, Telemetry):
- **Avoid running wires across the entire diagram**.
- Use a **Dedicated Vertical Side Column**:
  - Main diagram area: $X: 100 \rightarrow 1280$
  - Side column frame: $X: 1340 \rightarrow 1650, Y: 150 \rightarrow 1050$
  - Place OpenTelemetry, Prometheus, IAM, Vault in the side column.
  - Connect core services to the side column with dashed, subtle connectors (`strokeStyle="dashed"`, `strokeColor="#868e96"`).

---

## 3. Shape Mapping Conventions

| Component Type | Excalidraw Tool | Recommended Dimensions | Recommended Colors |
|---|---|---|---|
| Client / Frontend | `add_rectangle` | $160-200\text{px} \times 70-80\text{px}$ | Stroke `#1971c2`, Fill `#e7f5ff` |
| Gateway / Reverse Proxy | `add_rectangle` | $180-220\text{px} \times 70-80\text{px}$ | Stroke `#0c8599`, Fill `#e3fafc` |
| Microservice / Backend | `add_rectangle` | $160-200\text{px} \times 75-85\text{px}$ | Stroke `#5f3dc4`, Fill `#f3f0ff` |
| Database / Persistence | `add_rectangle` or `add_circle` | $140-180\text{px} \times 70-80\text{px}$ | Stroke `#2f9e44`, Fill `#ebfbee` |
| Queue / Message Stream | `add_rectangle` | $160-200\text{px} \times 70-80\text{px}$ | Stroke `#d9480f`, Fill `#fff4e6` |
| Security / Firewall | `add_rectangle` | $160-200\text{px} \times 70-80\text{px}$ | Stroke `#c92a2a`, Fill `#ffe3e3` |
| External 3rd Party | `add_rectangle` | $160-200\text{px} \times 70-80\text{px}$ | Stroke `#495057`, Fill `#f1f3f5` |
| System / VPC Boundary | `add_frame` | $1400-1600\text{px} \times 140-180\text{px}$ | Border `#1e1e1e`, Fill `transparent` |
