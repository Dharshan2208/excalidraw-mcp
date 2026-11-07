# Visual Anti-Patterns Catalog

This catalog documents common visual defects that make diagrams look machine-generated, cluttered, or difficult to read, along with concrete corrective actions.

---

## Anti-Pattern 1: The Rainbow Clown Show
- **Symptom**: Every box has a different vivid color (red, blue, green, orange, purple, pink) with no semantic meaning.
- **Why it fails**: Colors lose their communicative power. Viewers cannot distinguish critical paths from secondary components.
- **Correction**: Adopt the **60-30-10 rule**. Use neutral fills (`#ffffff`, `#f8f9fa`) for 70% of elements, one primary accent color for the core system, and at most two functional accents (e.g., green for data, amber for queues).

---

## Anti-Pattern 2: The Monolithic Monolith
- **Symptom**: All nodes are identical squares or rectangles of identical size regardless of role, hierarchy, or content length.
- **Why it fails**: Creates a wall of identical boxes where the eye cannot establish hierarchy.
- **Correction**: Use purposeful dimensions:
  - Clients / Entry: `180 x 50px` (pill/rounded).
  - Main services: `200 x 70px` or `220 x 80px`.
  - Databases: Cylinders or distinct tinted rectangles with `[(DB)]` badge.
  - Queues / Buffers: Narrow elongated rectangles (`200 x 45px`).
  - Decisions: Diamonds (`add_diamond`, min `180 x 110px`).

---

## Anti-Pattern 3: Edge-to-Edge Frame Cramming
- **Symptom**: Child elements touch or cross the perimeter border of their containing frame or boundary box.
- **Why it fails**: Looks accidental and triggers geometry warnings in `auto_fix_layout`.
- **Correction**: Maintain strict frame padding:
  - Top header padding: `50px` (clearing frame label).
  - Left / Right / Bottom margins: $\ge 40\text{px}$.

---

## Anti-Pattern 4: The Spaghetti Highway
- **Symptom**: Straight diagonal arrows criss-crossing over boxes, labels, and other arrows.
- **Why it fails**: Impossible to trace flow lines; looks chaotic and unverified.
- **Correction**:
  - Always enable `elbowed=True` on `connect` tool calls.
  - Align boxes along shared horizontal or vertical axes.
  - Maintain a corridor clearance of $\ge 15\text{px}$ around shapes.
  - Maintain $\ge 24\text{px}$ lane spacing between parallel connectors.

---

## Anti-Pattern 5: Text Overflows & Micro-Typography
- **Symptom**: Text strings clipped outside node borders, or microscopic font sizes (`fontSize: 10`) used to compress sentences into small shapes.
- **Why it fails**: Illegible at standard zoom levels and unreadable when exported to PNG.
- **Correction**:
  - Never use font sizes below `14px` for readable elements (`12px` strictly for secondary port badges).
  - Dimension shapes with proportional margins: width $\ge \text{longest line length} \times 9\text{px} + 30\text{px}$.
  - Break long titles into 2 lines.

---

## Anti-Pattern 6: Missing Connection Labels
- **Symptom**: Naked arrows connecting boxes without indicating the protocol, action, or data payload.
- **Why it fails**: The viewer is left guessing whether the connection is synchronous HTTP, asynchronous Kafka, SQL, or WebSocket.
- **Correction**: Pass `label="GET /orders"`, `label="Kafka Event"`, or `label="SQL read"` to the `connect` call.
