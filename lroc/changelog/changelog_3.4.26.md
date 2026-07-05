# Changelog v3.4.26 — Phantom Page Centreline Trim

Date: 2026-06-16 AEST

## Fixes

- Reworked the terminal article page-count test used by both the Article Library A4 preview and Issue Builder.
- Windowed page measurement now counts a text/media rectangle only when its centre point is inside the clipped page window, preventing edge slivers from creating a phantom final page.
- Added visible A4 preview renderer diagnostics showing per-page area/text/media stats to make any remaining ghost page measurable rather than guesswork.
- Preserved caption editing, advert caption suppression, placement status sync, article-chain locking, manual image flow controls, and deploy helper v1.13.

## Validation

- `python3 -m py_compile lroc/deployer/deploy_helper.py lroc/lambda/member_files.py lroc/lambda/magazine_api.py`
- `node --check lroc/site/app.js`
- `node --check lroc/site/service-worker.js`
- `node --check lroc/site/expo/expo.js`
