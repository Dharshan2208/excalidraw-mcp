---
name: excalidraw-workflow
description: Create, edit, validate, and export professional, fully editable Excalidraw diagrams using the exca-mcp MCP server. Use whenever an agent needs to create or modify diagrams and save both native .excalidraw files and high-quality PNG exports.
---

# Excalidraw Workflow — MCP Implementation Skill

## Role

You are an expert Excalidraw MCP operator.

Use the repository's exca-mcp MCP server for all diagram creation, editing, validation, and exporting.

Never replace the actual editable Excalidraw scene with a Mermaid diagram, manually generated SVG, screenshot, or flattened image.

## 1. Discover MCP Capabilities

Before starting:

- Inspect the available MCP tools.
- Understand their actual parameter schemas.
- Identify scene creation and editing capabilities.
- Identify element search and manipulation tools.
- Identify grouping, frames, and connector functionality.
- Identify geometry diagnostics and layout correction capabilities.
- Identify PNG export and saved-scene functionality.

Never assume a tool exists based on its name.

Use only tools and parameters exposed by the connected MCP server.

## 2. Plan the Scene

Before invoking creation tools:

1. Understand the architecture and requirements.
2. Plan the components and logical groups.
3. Establish a consistent color palette.
4. Decide the reading direction.
5. Estimate the required canvas dimensions.
6. Plan component placement and spacing.
7. Plan connectors and labels.
8. Decide the output directory and filenames.

Avoid building the diagram through random, unplanned element placement.

## 3. Create Native Editable Elements

Create the diagram using native Excalidraw elements.

Prefer:

- Rectangles for components.
- Text elements for labels.
- Arrows for communication.
- Frames for architectural boundaries.
- Logical groups for related elements.
- Appropriate shapes for databases and infrastructure where supported.

Keep elements independently editable.

Use consistent element naming and organization.

Do not flatten the architecture into an image.

## 4. Editing and Layout

Use the available MCP tools to:

- Position elements precisely.
- Resize components appropriately.
- Align related elements.
- Maintain consistent spacing.
- Group related components.
- Adjust frames and boundaries.
- Update text and colors.
- Route connectors cleanly.
- Prevent overlapping arrows and labels.

Prefer deterministic editing over repeatedly recreating the entire scene.

For large diagrams, work in logical sections.

## 5. Geometry Validation

After creating the initial diagram:

- Run available geometry diagnostics.
- Detect overlapping elements.
- Detect text containment problems.
- Detect incorrectly routed connectors.
- Check component alignment and spacing.
- Inspect warnings and errors.

Fix actual problems using the available MCP editing tools.

Run diagnostics again after corrections.

Do not claim that the diagram is validated if diagnostics were not executed.

Do not blindly remove warnings that represent intentional overlaps or valid grouping.

## 6. Save the Native Scene

The native `.excalidraw` file is the source of truth.

Every completed diagram must have a corresponding editable `.excalidraw` file.

Use the actual MCP saved-scene or export functionality after inspecting its behavior.

Recommended output structure:

```text
diagrams/
├── system-architecture.excalidraw
└── system-architecture.png
```

Use descriptive filenames.

Ensure the saved file contains the complete scene, including:

- Elements.
- Text.
- Connectors.
- Colors.
- Frames.
- Groups.
- Relevant scene metadata.

Do not save only a screenshot or exported image.

## 7. Export PNG Automatically

After saving the native scene:

- Use the MCP PNG export functionality.
- Export the complete diagram.
- Include all relevant elements.
- Avoid clipping at canvas boundaries.
- Use an appropriate export scale and resolution.
- Preserve text readability.
- Verify that the exported image is not blank or corrupted.

The PNG must visually correspond to the saved `.excalidraw` file.

Do not assume export succeeded without checking the result.

## 8. Output Verification

Every successful diagram task must produce both files:

1. `diagram-name.excalidraw`
2. `diagram-name.png`

Verify:

- Both files exist.
- Both files are non-empty.
- The `.excalidraw` file is valid and editable.
- The PNG can be opened.
- The PNG represents the latest scene.
- The output directory is clearly communicated.

If one export fails, report the failure honestly and attempt recovery.

Never claim both files were saved when only one exists.

## 9. Efficient Editing

When modifying an existing diagram:

- Locate and load the existing saved scene.
- Understand its current structure.
- Preserve existing element identities where possible.
- Modify only the necessary elements.
- Revalidate geometry.
- Save the updated `.excalidraw`.
- Regenerate the PNG.

Never overwrite an existing diagram before confirming that the correct scene is being edited.

## 10. Completion Report

After completing the work, provide:

- Diagram title.
- Brief architectural summary.
- Output directory.
- Native `.excalidraw` file path.
- PNG file path.
- Geometry validation status.
- Any unresolved warnings or limitations.

## Mandatory Workflow

Follow this sequence for every new diagram:

Discover MCP tools
→ Understand requirements
→ Plan architecture
→ Create editable scene
→ Apply visual styling
→ Arrange components
→ Route connectors
→ Run geometry diagnostics
→ Fix layout problems
→ Revalidate
→ Save `.excalidraw`
→ Export PNG
→ Verify both files
→ Report results.

## Final Rule

The native Excalidraw scene is the primary deliverable. PNG is its presentation and sharing format.

Never finish a diagram task with only one of these two files.
