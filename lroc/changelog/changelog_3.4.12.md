# LROC v3.4.12 — Article Continuation Window Fix

Timestamp: 2026-06-14 AEST

## Fixes

- Fixed TinyMCE article continuation pages showing the first page repeatedly when the preview/editor path lost the saved CSS column-window mode or X offset.
- Continuation pages now reconstruct the horizontal page-window offset from the article page index or generated slot id when needed.
- Changed the rendered article window from negative-left positioning to a translateX offset, making the clipping more resilient across proof/editor refreshes.
- Kept the v3.4.11 native/TinyMCE HTML path so repaired font formatting is preserved.
- Kept the explicit bullet/number fallback styling introduced for generated article pages.

## Notes

This is intentionally a narrow correction after v3.4.11 restored the expected three-page count and retained font formatting. Existing pages generated before v3.4.12 should be re-placed fresh so their page-window metadata is regenerated cleanly.
