# Changelog v3.4.19 — A4 Preview Phantom Page Trim

Timestamp: 2026-06-15 20:18:42 AEST

## Changed
- Trimmed Article Library A4 layout preview pages using actual clipped page-window content rather than broad multicolumn block rectangles.
- Applied the same meaningful-window page count to Issue Builder article placement so empty continuation pages are not assigned.
- Preserved the v3.4.13 caption workflow and v3.4.15 manual image earlier/later controls.
- Preserved the v3.4.18 local Refresh A4 preview button wiring.

## Fixed
- A phantom final article page could still appear when the browser's multicolumn layout exposed tiny or broad measurement rectangles beyond the real visible article end.
- The A4 preview could show an extra meaningless page even when the article finished on page 2.

## Notes
- The A4 preview refresh remains local/client-side, so the browser Network tab is not expected to show activity for that button.
- Re-place existing articles after deployment so old continuation metadata is not reused.
