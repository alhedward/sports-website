# LROC v3.4.6 — Article Renderer Viewport Stabilisation

Generated: 2026-06-14 AEST

## Fixes

- Clamped TinyMCE article preview fitting so Issue Builder never scales generated article pages above 100%.
- Added a default fitted transform before JavaScript measurement runs to reduce the oversized flicker when toggling proof/editor view.
- Positioned the MCE article window and diagnostics note absolutely so the note does not consume article layout height.
- Quarantined TinyMCE article images from the generic Issue Builder thumbnail CSS that forced all images to 100% width / 180px height.
- Kept v3.4.5 page-fragment preservation and repeated-title suppression intact.

## Test focus

- Place a TinyMCE Article Library article across multiple issue pages.
- Toggle proof/editor view repeatedly and confirm the page does not briefly overfit/zoom.
- Confirm article images render at their intended magazine size instead of becoming a large oval/placeholder.
- Confirm pages 1, 2 and 3 remain in the correct selected issue pages.
