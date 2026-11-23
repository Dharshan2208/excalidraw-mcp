# Entry Tool Decision Tree

Choose the right initial tool based on diagram category, topology, and required fidelity:

```
                                 [Diagram Request]
                                         │
                    Is it a quick flowchart or state diagram
                         easily expressed in Mermaid syntax?
                                    /         \
                                (Yes)         (No)
                                 /               \
              [generate_diagram(format="mermaid")] Is it a simple 3-8 box
                     (CORE: 12 tools)              linear architecture?
                                                /           \
                                            (Yes)           (No)
                                             /                 \
            [generate_diagram(format="architecture")]      Is EXCALIDRAW_TOOLSET=full
                     (FULL: 21 tools)                      and graph is algorithmic?
                                                               /              \
                                                           (Yes)              (No)
                                                            /                    \
                                         [generate_diagram(format="graph")]  [Primitives / batch_mutate]
                                                   (FULL: 21 tools)                 (CORE: 12 tools)
                                                                           *Recommended for all
                                                                           production architecture*
```

---

## Tool Tradeoff Matrix

| Tool | Toolset | Best Used For | Strengths | Limitations |
|---|---|---|---|---|
| `generate_diagram(format="mermaid")` | **CORE** | Pipelines, sequential flows, state machines, quick flowcharts | Extremely fast; native subgraph clustering; automatic text containment | Limited custom layout tiers; cannot style individual nodes with distinct palettes in one call |
| `generate_diagram(format="architecture")` | **FULL** | Quick 1-tier shorthand (`"box: Web, db: SQL"`) | Fast syntax DSL; instant horizontal layout | Rigid grid flow; global styling only; no multi-tier framing |
| `generate_diagram(format="graph")` | **FULL** | Large algorithmic node-edge graphs, topology exports | Deterministic rank layering; cluster frames; returns ID mapping | Requires `EXCALIDRAW_TOOLSET=full`; rigid auto-placement |
| **Primitives (`create_shape`, `create_connector`, `batch_mutate`)** | **CORE** | **Production system architecture, multi-tier cloud diagrams** | **100% control over tiers, frames, custom semantic colors, and exact docking** | Requires calculating $(x, y)$ coordinates or batch mutation structure |

---

## When to Use Primitives (`create_shape`, `add_frame`, `create_connector`, `batch_mutate`)

Always choose Primitives for:
1. **Multi-tier enterprise architectures** (e.g. Clients $\rightarrow$ Gateway $\rightarrow$ Services $\rightarrow$ Storage $\rightarrow$ External).
2. **Diagrams with specialized boundaries** (VPCs, Kubernetes clusters, security zones).
3. **Diagrams requiring semantic color-coding** (different colors per layer or component type).
4. **Diagrams with side columns or banners** (Auth, Observability, Cross-cutting concerns).
