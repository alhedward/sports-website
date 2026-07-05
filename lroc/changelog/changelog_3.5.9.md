# v3.5.9 — Front Cover Auto-Balanced Bottom Row

- Added automatic balancing for the two bottom-banner second-row cells.
- The lower row now estimates each text group’s rendered width and adjusts the cell split so the start of the left text and the end of the right text have matching outside margins.
- The calculated split is clamped to a sensible 30%–70% range to avoid extreme layouts with very long URLs.
- If only one lower-row cell has text, it is centred across the full lower row.
- If both lower-row cells are blank, the existing rule remains: the top row vertically centres in the bottom bar.
- No new editor control was added; balancing is automatic.
