# LROC v3.4.28 — A4 Diagnostics / Post-Candidate Phantom Prune

Timestamp: 2026-06-16 18:27:55 AEST

## Focus

This release keeps the v3.4.27 article renderer path but makes the phantom-page debugging visible and moves the final page trim closer to the generated page candidates.

## Changes

- A4 preview diagnostics are now always shown under the preview header.
- Diagnostics include final page count, clipped-window count, preliminary count, post-Scrooge count, scroll/content width counts and per-window page stats.
- The diagnostics panel opens automatically when the renderer still reports more than two pages or when clipped count and final count disagree.
- Hidden page-window measurement now uses invisible in-page measurement windows rather than far-offscreen fixed windows, which could under-read CSS multicolumn continuation pages in some browsers.
- Added a post-candidate Scrooge prune that removes empty trailing page candidates after the candidate count is known, while preserving at least two pages when non-window measurements agree the article has a continuation.
- Removed the top Magazine Production overview cards for Upload limit, Print quality and Current issue from the main screen to reduce clutter.

## Preserved behaviour

- Caption double-click editing remains intact.
- Insert Advert caption suppression remains intact.
- Manual image earlier/later controls remain intact.
- A4 preview refresh remains responsive.
- Article placement status sync remains intact.
- Article-chain locking remains intact.
- Deploy helper v1.13 remains included in `lroc/deployer/deploy_helper.py`.
