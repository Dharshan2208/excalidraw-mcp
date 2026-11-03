# 10-Point Diagram Delivery Checklist

Before handing off an Excalidraw diagram to a user or commiting assets, run through this comprehensive quality gate. Every item must pass.

---

| # | Inspection Point | Verification Method | Pass Criteria |
| :---: | :--- | :--- | :--- |
| **1** | **Geometry Diagnostics** | Run `auto_fix_layout(dry_run=True)` | `status == "no_changes_needed"` or `len(initial_issues) == 0`. |
| **2** | **No Element Overlaps** | Inspect `auto_fix_layout` report | Zero unintentional box-over-box overlaps. (Intentional overlaps tagged with `customData: {"allow_overlap": true}`). |
| **3** | **Frame Containment** | Verify frame child coordinates | Every child node sits strictly inside frame boundaries with $\ge 40\text{px}$ perimeter margin. |
| **4** | **Connector Binding** | Check connector properties in `get_scene` | Both `startBinding` and `endBinding` are populated with non-null `elementId`. |
| **5** | **No Unlabeled Branches** | Trace diamond and decision outlets | Every outbound decision line has `label="Yes"`, `label="No"`, or explicit condition. |
| **6** | **Orthogonal Routing** | Check connector geometry | Connectors use `elbowed=True`, avoiding straight diagonal crossings through shapes. |
| **7** | **Visual Polish & Hierarchy** | Call `preview(scale=1.0)` and view image | Title is prominent ($28\text{px}$), frames clear ($20\text{px}$), labels legible ($\ge 14\text{px}$), balanced margins. |
| **8** | **Semantic Palette Restraint**| Visual inspection of colors | Adheres to 60-30-10 rule (2-4 semantic colors max; neutral backgrounds). |
| **9** | **Editable State Preserved** | Inspect element metadata | No shapes left locked (`locked: true`). All labels bound to their host elements. |
| **10**| **Dual Format Delivery** | Execute export tools | Both high-res PNG (`export_png`) and native `.excalidraw` (`save` or `export_scene`) are produced. |

---

## Handoff Communication Template

When presenting the completed diagram to the user, include this concise handoff note:

```markdown
### Diagram Delivery

The diagram has been designed, verified against layout defects, and exported in dual formats:

1. **Native Editable File**: Saved as `{name}.excalidraw` (can be dragged directly into [excalidraw.com](https://excalidraw.com)).
2. **High-Resolution PNG**: Saved as `{name}.png` (ready for documentation, READMEs, and presentations).

#### Editability Features
- **Bound Connectors**: Moving any service or database box will automatically stretch and reroute attached arrows.
- **Embedded Labels**: Shape labels are bound to their respective containers.
- **Grouped Tiers**: Boundaries and architectural zones are organized logically.
```
