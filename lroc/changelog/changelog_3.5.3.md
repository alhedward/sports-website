# LROC v3.5.3 — True TinyMCE A4 Composer Geometry

Date: 2026-06-19 17:24 AEST

## Changed

- Made the Article Library TinyMCE editor behave as an A4 composer surface instead of a generic web text box.
- The TinyMCE iframe body now uses the same core A4 render geometry used by A4 preview and Issue Builder:
  - 700 px content width
  - 990 px content height guide
  - matching column gaps for 1/2/3 column article work
- Added a subtle in-editor A4 content surface with page-height marker guidance.
- Kept the separate A4 preview as confirmation while making the editor itself a closer working representation.
- No GrapesJS/Layout Lab code is included.

## Notes

This is a geometry foundation pass. It does not yet make TinyMCE a multi-page issue compositor, but it moves the Article Library editor toward the intended A4 page-composer workflow.
