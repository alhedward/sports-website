# v3.4.21 — A4 Preview / Issue Builder Continuation Repair

Timestamp: 2026-06-15 20:32 AEST

## Fixed

- Repaired the v3.4.20 regression where the Article Library A4 preview and Issue Builder could render only the first article page.
- Keeps real continuation pages when the block estimator and column/content measurements agree that the article continues beyond page 1.
- Keeps the clipped-window meaningful-page test as a trailing ghost-page trim signal rather than the sole page-count authority.
- Removes empty inline advert wrappers left behind by TinyMCE when an inserted advert is deleted.

## Preserved

- Insert Advert continues to suppress captions.
- Normal article image captions and double-click caption editing remain unchanged.
- The responsive Refresh A4 preview button remains unchanged.
- The LROC footer style remains unchanged.
