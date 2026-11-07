# Semantic Palette Catalog

This catalog defines verified, professional color schemes optimized for Excalidraw diagrams. Every palette uses a restrained set of semantic colors grounded in the **60-30-10 rule**:
- **60% Neutrals**: Canvas white, background containers, borders, and general body nodes.
- **30% Structure**: Core processing services, main components, and standard relationship links.
- **10% Accent**: Entry points, external systems, warnings, queues, or failure states.

---

## Palette A: Modern Cloud & Distributed Systems (Default)

Ideal for microservices, cloud infrastructure (AWS/GCP/Azure), and distributed backends.

| Role | Semantic Purpose | `backgroundColor` | `strokeColor` | `fillStyle` |
| :--- | :--- | :--- | :--- | :--- |
| **Canvas / Frame** | Trust / VPC boundary | `#f8f9fa` | `#ced4da` | `solid` |
| **Neutral Node** | General service / component | `#ffffff` | `#495057` | `solid` |
| **Primary Service** | Core business logic / API | `#e7f5ff` | `#1971c2` | `solid` |
| **Data Store** | Persistent DB / Cache | `#e6fcf5` | `#0ca678` | `solid` |
| **Queue / Stream** | Kafka / SQS / Asynchronous | `#fff9db` | `#f59f00` | `solid` |
| **External / Untrusted** | Third-party API / Webhooks | `#fff5f5` | `#e03131` | `hachure` |
| **Text Dark** | Primary labels | N/A | `#212529` | N/A |
| **Text Muted** | Metadata, ports, subtitles | N/A | `#868e96` | N/A |

---

## Palette B: Warm Editorial & Product Workflows

Ideal for high-level customer journeys, product architecture, and enterprise integration reviews.

| Role | Semantic Purpose | `backgroundColor` | `strokeColor` | `fillStyle` |
| :--- | :--- | :--- | :--- | :--- |
| **Canvas / Frame** | Business domain boundary | `#fcfaf7` | `#d8d2c4` | `solid` |
| **Neutral Node** | Standard action step | `#ffffff` | `#49423d` | `solid` |
| **User / Client** | Customer touchpoint / UI | `#f3f0ff` | `#6741d9` | `solid` |
| **Integration** | Partner services / APIs | `#fff4e6` | `#d9480f` | `hachure` |
| **Terminal / Success** | Approved / Completed | `#ebfbee` | `#2b8a3e` | `solid` |

---

## Palette C: Technical Monospaced & Security

Ideal for security threat modeling, compliance boundaries, and kernel/infrastructure internals.

| Role | Semantic Purpose | `backgroundColor` | `strokeColor` | `fillStyle` |
| :--- | :--- | :--- | :--- | :--- |
| **Public / Edge** | Internet / Untrusted zone | `#fff5f5` | `#c92a2a` | `solid` |
| **DMZ / Gateway** | Ingress controller / Envoy | `#fff9db` | `#e67700` | `solid` |
| **Secure Enclave** | Internal network / Vault | `#e7f5ff` | `#1864ab` | `solid` |
| **Isolation Barrier** | Hard network boundary | Transparent | `#868e96` (dashed) | N/A |

---

## Applied Fill Styles & Roughness Guidelines

```python
# Modern clean architecture look:
roughness = 1  # Subtle organic human touch, not rigid or sloppy
fillStyle = "solid"  # Crisp readability for node fills
roundness = "adaptive"  # Soft rounded corners on boxes

# Sketchy / Ideation look:
roughness = 2  # Hand-drawn artistic feel
fillStyle = "hachure"  # Textured diagonal hatch lines
fontFamily = "excalifont"  # Handwritten typography

# Strict Technical / Network topology:
roughness = 0  # Crisp geometric blueprint lines
fillStyle = "solid"
roundness = "sharp"  # Square rectangular corners
fontFamily = "sans-serif"  # Precise clean typography
```
