# LROC v3.4.5 — Article Renderer Restoration

Timestamp: 2026-06-14 12:08 AEST

## Summary

Restores TinyMCE article rendering in Issue Builder after the v3.4.4 page-fragment preservation patch proved too narrow. The generated article page payload is now carried through preview/editor refreshes as hidden structured metadata, while still suppressing repeated external Article Library slot headers.

## Changes

- Preserved generated TinyMCE article page HTML through Issue Builder preview refreshes.
- Preserved full article HTML, page fragment HTML, page index/count, renderer geometry, column count, and diagnostics metadata as a hidden payload in generated article page editors.
- Added TinyMCE article page as an explicit render-mode option so generated pages do not fall back to the default/blank render mode when editor controls are rebuilt.
- Merged dynamic slot definitions and stored slot values before rendering generated article pages, so pages can render even if one side of the metadata is temporarily missing.
- Kept whitespace-only optional header overrides blank.
- Kept repeated external content slot titles suppressed for generated TinyMCE article pages.
- Updated service-worker cache namespace.

## Validation

```bash
python3 -m py_compile lroc/lambda/member_files.py lroc/lambda/magazine_api.py
node --check lroc/site/app.js
node --check lroc/site/service-worker.js
node --check lroc/site/expo/expo.js
```

## Testing notes

After deployment, re-place the article from Article Library rather than relying on any v3.4.4 pages that may already have been saved with blanked page-fragment metadata.

The remaining visual tuning item is bottom-fill/column balance around large figures and manual image placement.
