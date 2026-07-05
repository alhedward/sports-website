# LROC v3.4.7 — Article Renderer Whitespace Reduction

Generated: 2026-06-14 AEST

## Fixes

- Added whitespace-reduction logic to the TinyMCE article paginator.
- When a figure/image block would leave a large white hole at the bottom of a non-final page, the renderer now first attempts to shrink that movable media block to fit the remaining space.
- If shrinking would not produce a sensible fit, the renderer can pull a small number of following text blocks forward and move the image to the next page.
- Added diagnostics counters for whitespace adjustments, pulled-forward text blocks and shrunk media blocks.
- Added CSS for shrink-to-fill article figures/images so preview and proof rendering use the same adjusted media sizing.

## Intent

The article renderer should favour full magazine pages. Large blank areas caused by indivisible image blocks are now treated as layout problems to repair, rather than accepted as normal pagination.

The final page may still contain white space if the article genuinely ends there.

## Test focus

- Place the same multi-page TinyMCE article used for v3.4.6 testing.
- Confirm all pages still land in the expected Issue Builder pages.
- Check non-final pages for large blank bottom regions, especially before/after images.
- Confirm images remain visible and readable after automatic shrink-to-fit adjustments.
- Confirm proof/editor toggling still does not trigger the old 150% overfit flicker.
