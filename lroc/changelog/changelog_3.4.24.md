# LROC v3.4.24 - Article Chain Lock Propagation

Released: 2026-06-15 AEST

## Changed

- Added article-chain lock propagation in Issue Builder.
- When page 1 of a placed/generated article is locked, continuation pages for the same article are automatically locked as well.
- Continuation matching uses the placed article content item and generated article/page metadata, including TinyMCE article pages, source pages and composer/generated article pages.
- Existing locked/fixed pages, front cover and back-cover advert pages remain protected and are not modified.

## Preserved

- v3.4.23 Article Library placement status sync.
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
