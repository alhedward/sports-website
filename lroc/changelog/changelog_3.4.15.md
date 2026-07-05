# LROC v3.4.15 — Article Flow / Phantom Page Fix

Date: 2026-06-15 18:37 AEST

## Summary

This release keeps the v3.4.13 caption fix and the v3.4.12 continuation-window renderer, then narrows in on the two remaining live-test defects from v3.4.14:

- whitespace mitigation did not visibly change the article body flow;
- Issue Builder still allocated a phantom final continuation page when the article had already ended.

## Changes

- Changed **Image tools → Move image down/up** from a CSS margin nudge into a real article-flow reorder.
  - “Move image later” moves the selected figure after the next article block.
  - “Move image earlier” moves it before the previous article block.
  - This changes the source order in TinyMCE so pagination can genuinely fill text before the image.
- Added automatic image-flow optimisation during article placement.
  - When a movable image would strand a large white hole at the bottom of a column, the renderer can pull following text blocks ahead of that image for the placed issue pages.
  - This keeps semantic HTML such as lists/headings intact and avoids returning to the broken explicit-column packer from v3.4.7/v3.4.9.
- Reworked phantom page detection.
  - The page count now scans actual rendered text/image/table rectangles in each page window.
  - Empty multicolumn tail reservations no longer force a blank final Issue Builder page.
- Updated pagination diagnostics:
  - `measuredContentPageCount`;
  - `autoMovedImages`;
  - `pulledForwardTextBlocks`;
  - `shrunkMediaBlocks`.
- Bumped renderer/composer metadata to 3.4.15.
- Bumped service-worker cache namespace.

## Notes

Captions remain as implemented in v3.4.13: double-click image caption editing works and filename-style captions stay suppressed in Issue Builder preview.

This is still a web preview renderer. The goal is magazine-like dense flow without damaging the Article Library source formatting.
