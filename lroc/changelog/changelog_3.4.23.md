# LROC v3.4.23 - Article Placement Status Sync

Released: 2026-06-15 AEST

## Changed

- Fixed the Article Library page selector so it recognises generated article/source pages already placed in Issue Builder.
- Pages containing TinyMCE article windows, source document pages, composer pages, or content items whose `assignedPageNumbers` include that page now show as occupied instead of `blank/available`.
- Added clearer page labels such as `contains placed article` in the Article Library placement selector.
- Left the actual placement/reset behaviour unchanged: generated article pages can still be replaced intentionally when placing/reflowing an article.

## Preserved

- v3.4.22 phantom-page trim logic.
- v3.4.20 Insert Advert caption suppression.
- v3.4.13 image caption double-click/edit behaviour.
- v1.13 deploy helper quick deploy prompt in `lroc/deployer/deploy_helper.py`.
- Existing LROC footer style.

## Validation

```bash
python3 -m py_compile lroc/deployer/deploy_helper.py lroc/lambda/member_files.py lroc/lambda/magazine_api.py
node --check lroc/site/app.js
node --check lroc/site/service-worker.js
node --check lroc/site/expo/expo.js
```
