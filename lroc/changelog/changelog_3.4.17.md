# LROC v3.4.17 — Article Preview Alignment / Page-Break Cleanup

## Summary

This release keeps the working caption and manual image-flow controls, then fixes the remaining Article Library preview confusion: the A4 layout preview now uses the same windowed TinyMCE article renderer as the Issue Builder placement path instead of its older vertical-scroll approximation.

## Changes

- Aligned the Article Library A4 layout preview with the Issue Builder TinyMCE article renderer.
- Preview pages now use the same horizontal page-window offsets as placed article pages.
- Preview page count now comes from the renderer's meaningful content page windows rather than old vertical `scrollHeight` estimation.
- Strips obsolete TinyMCE/page-break marker `<hr>` elements during Article Library HTML normalisation.
- Removed the TinyMCE pagebreak toolbar/plugin entry and the Blocks menu manual page-break item.
- This should stop stale or misleading page-break markers from forcing a blank continuation page.
- Kept the successful v3.4.13 image-caption behaviour.
- Kept the v3.4.15 manual image earlier/later flow controls.
- Kept the LROC footer style for placed Issue Builder pages.
- Updated VERSION to 3.4.17.
- Updated service-worker cache namespace.
