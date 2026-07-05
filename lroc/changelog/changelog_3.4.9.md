# LROC v3.4.9 - Article Renderer No-Blank Refinement

Timestamp: 2026-06-14 15:13:21 AEST

## Purpose

Tighten the TinyMCE article renderer against the supplied A4 two-column reference PDF. The goal is to keep non-final article pages visually filled, with movable images resized/repositioned by the renderer where needed, while retaining the existing LROC issue footer styling.

## Changes

- Restored bullet/list marker reliability for generated article pages.
- Fixed list fragment generation so split list items do not emit duplicate class attributes.
- Added explicit two-column page fragments for generated TinyMCE article pages instead of relying on browser CSS multi-column balancing.
- Added per-column media safety so oversized movable image/figure blocks can be reduced before they strand large white areas.
- Added heading/media shrink-to-fit handling so a heading followed by an image does not force a premature page break when the image can be reasonably reduced.
- Added renderer diagnostics for explicit columns and media column adjustments.
- Kept the existing LROC footer style; this change only affects generated article body layout.

## Validation

- python3 -m py_compile lroc/deployer/deploy_helper.py
- python3 -m py_compile lroc/lambda/member_files.py lroc/lambda/magazine_api.py
- node --check lroc/site/app.js
- node --check lroc/site/service-worker.js
- node --check lroc/site/expo/expo.js
