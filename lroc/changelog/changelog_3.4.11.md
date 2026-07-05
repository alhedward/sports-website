# Changelog v3.4.11 — Article Renderer Page Window Fix

Timestamp: 2026-06-14 15:43:41 AEST

## Why this release exists

v3.4.10 produced a better looking native two-column article flow, but testing showed two continuation problems:

- generated continuation pages could render the first article window again instead of their own page window;
- the page count could be over-estimated because the old block-height estimate was still allowed to add pages even when the browser's native multi-column sheet measured fewer pages.

Bullets also needed a stronger fallback because native list markers can still vanish inside clipped proof-page/article-window contexts.

## Changes

- Preserves `mcePageOffsetXPx`, page stride, column gap, and image cap values through preview/editor/save round-trips.
- Uses the browser's native multi-column scroll width as the authority for generated page count, with manual page breaks as a minimum only.
- Keeps the original TinyMCE HTML intact for generated article pages.
- Adds explicit CSS bullet/number marker fallback for generated TinyMCE article pages and the hidden measurement body.
- Keeps the existing LROC article footer style.
- Keeps deployer integration from v3.4.8.

## Notes

This release is deliberately narrow: it fixes repeated first-page windows and list-marker visibility without reintroducing the destructive block packer from v3.4.7/v3.4.9.
