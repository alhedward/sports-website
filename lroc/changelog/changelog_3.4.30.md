# LROC v3.4.30 — Article Image Fine Border

Timestamp: 2026-06-16 19:54:59 AEST

## Changes

- Added a subtle fine border around normal article images so floated and full-column images read as placed magazine objects.
- Applied the border consistently in:
  - Article Library TinyMCE editor
  - A4 preview
  - Issue Builder / build preview
  - hidden article measurement render paths
- Explicitly excludes inline adverts from the article-image border because advert artwork should remain untouched/no-caption/no-float.

## Preserved behaviour

- v3.4.29 article image float layout controls remain intact.
- v3.4.28 phantom-page pruning and visible diagnostics remain intact.
- Caption double-click editing remains intact.
- Insert Advert caption suppression remains intact.
- Manual image earlier/later flow controls remain intact.
- Article placement status sync and article-chain locking remain intact.
- Deploy helper v1.13 remains included in `lroc/deployer/deploy_helper.py`.

## Testing notes

1. Open an Article Library article containing normal images.
2. Confirm full-column and floated article images show a fine border in the editor and A4 preview.
3. Place the article fresh into Issue Builder and confirm the border appears there as well.
4. Confirm inserted adverts do not gain an image border or caption.
