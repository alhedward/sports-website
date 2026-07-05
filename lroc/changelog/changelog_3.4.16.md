# LROC v3.4.16 — Phantom Page Exorcist

## Summary

This release keeps the successful v3.4.13 caption controls and v3.4.15 manual image flow moves, and narrows the renderer work to two jobs: trim the phantom trailing continuation page when the article really finishes on page 2, and remove misleading in-editor page guide markers from the Article Library TinyMCE editor.

## Changes

- Added stricter per-page usage scoring for windowed multicolumn TinyMCE article pages.
- Counts page windows from actual rendered glyph/media rectangles instead of broad text block rectangles that can bleed into empty multicolumn windows.
- Trims a trailing continuation page when it has no meaningful text/media content.
- Added diagnostics for measured content page count and meaningful content page count.
- Removed the horizontal page-guide markers from the Article Library TinyMCE editing surface because they do not match final Issue Builder pagination.
- Kept the separate A4 layout preview panel.
- Kept image caption behaviour from v3.4.13.
- Kept manual image-flow ordering tools from v3.4.15.
- Updated VERSION to 3.4.16.
- Updated service-worker cache namespace.
