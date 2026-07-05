# LROC v3.4.14 — Article Continuation Trim / Image Nudge Controls

Date: 2026-06-15 18:06 AEST

## Summary

This release continues the v3.4.x magazine article renderer work. It keeps the v3.4.13 caption controls and focuses on the remaining renderer issues reported from live testing:

- avoid assigning a blank trailing article continuation page when the article has already finished;
- add manual selected-image placement nudging in the Article Library editor;
- preserve the existing LROC footer style and the v3.4.12/v3.4.13 continuation-window renderer path.

## Changes

- Added **Image tools** menu to the Article Library TinyMCE toolbar.
- Added manual selected-image controls:
  - caption selected image;
  - move selected image down one line;
  - move selected image up one line;
  - reset selected image position.
- Added `data-mag-image-nudge="down-N"` rendering/measurement CSS so image nudges affect both editor preview and final Issue Builder rendering.
- Changed article page-count detection so the native multicolumn renderer uses the right edge of real rendered content rather than raw `scrollWidth` alone.
- Added pagination diagnostics for the measured content right edge and the width used for page-count calculation.
- Bumped renderer/composer metadata to 3.4.14.
- Bumped service-worker cache namespace.

## Notes

This is still a controlled web preview renderer, not the final immutable PDF renderer. Image nudging is deliberately a small manual hint rather than a full desktop-publishing layout engine.
