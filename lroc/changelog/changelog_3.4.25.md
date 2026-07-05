# LROC v3.4.25 - Phantom Page Terminal Trim

Released: 2026-06-15 AEST

## Fixed

- Tightened the final article-page trim logic used by both the Article Library A4 preview and Issue Builder placement.
- The renderer now treats a tiny terminal text/glyph spill as overflow noise rather than as a meaningful continuation page.
- Added page-stat diagnostics to the article renderer output so future ghost-page cases can show which window was counted and why.

## Preserved

- v3.4.24 article-chain lock propagation.
- v3.4.23 Article Library placement status sync.
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
