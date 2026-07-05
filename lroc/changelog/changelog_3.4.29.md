# LROC v3.4.29 — Article Image Float Layout Modes

Timestamp: 2026-06-16 19:28:01 AEST

## Focus

This release adds controlled article-image placement modes so normal Article Library images can be full-column or floated left/right with text wrapping beside them.

## Changes

- Added visible Article Library image layout buttons:
  - Image full column
  - Float image left
  - Float image right
  - Reset image layout
- Added matching TinyMCE Image tools menu entries.
- Stores layout as `data-mag-image-layout` on normal article figures.
- Adds renderer/A4 preview/Issue Builder CSS for floated images, with captions kept under the image.
- Floating is deliberately disabled for inline adverts.
- Normalises invalid/old image layout attributes on save/preview.

## Preserved behaviour

- v3.4.28 phantom-page pruning and diagnostics remain in place.
- Caption double-click editing remains intact.
- Insert Advert caption suppression remains intact.
- Manual image earlier/later article-flow controls remain intact.
- A4 preview refresh remains responsive.
- Article placement status sync and article-chain locking remain intact.
- Deploy helper v1.13 remains included in `lroc/deployer/deploy_helper.py`.

## Testing notes

1. Open an Article Library article.
2. Click a normal image.
3. Try Float image left/right and refresh A4 preview.
4. Confirm text wraps beside the image and captions remain attached.
5. Confirm Insert Advert artwork does not accept/show caption or float layout.
