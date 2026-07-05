# LROC v3.4.22 - Article Phantom Page Trim / Deployer Quick Prompt

Released: 2026-06-15 AEST

## Changed

- Tightened the article renderer page-count path so the clipped A4 page-window pass becomes the final trim authority once it sees more than one real page.
- Prorated text contribution by the visible clipped rectangle area during page measurement, preventing a tiny sliver of paragraph/list text from being counted as a full phantom continuation page.
- Kept the non-window block/scroll estimates as a fallback only when the clipped page-window pass under-reads and reports a single page.
- Included deploy helper v1.13 in `lroc/deployer/deploy_helper.py`, adding the quick deploy confirmation prompt from the Latest package picker.

## Preserved

- Article image caption double-click behaviour from v3.4.13.
- Insert Advert caption suppression from v3.4.20.
- Responsive Refresh A4 preview button behaviour.
- Manual image earlier/later movement controls.
- Existing LROC footer style.

## Validation

```bash
python3 -m py_compile lroc/deployer/deploy_helper.py lroc/lambda/member_files.py lroc/lambda/magazine_api.py
node --check lroc/site/app.js
node --check lroc/site/service-worker.js
node --check lroc/site/expo/expo.js
```
