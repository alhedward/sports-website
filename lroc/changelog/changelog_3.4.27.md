# LROC v3.4.27 — Scrooge Phantom Page Prune

Timestamp: 2026-06-16 18:16:31 AEST

## Changed

- Added a final Scrooge terminal-page prune for generated TinyMCE article pages.
- Trailing page 3+ candidates are discarded when they look like empty spill/duplicate page windows rather than real article content.
- Page-break markers remain deprecated and stale manual-break markers no longer force generated continuation pages.
- Renderer diagnostics now include text samples for page-count debugging.

## Preserved

- Caption double-click editing.
- Insert Advert caption suppression.
- Manual image earlier/later controls.
- Responsive A4 preview refresh.
- Article placement status sync and article-chain locking.
- Deploy helper v1.13 in `lroc/deployer/deploy_helper.py`.
