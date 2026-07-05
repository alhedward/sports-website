# LROC v3.4.31 — Inline Advert Layout Modes

Timestamp: 2026-06-16 20:16:10 AEST

## Changes

- Added Article Library controls for adverts inserted through the **Insert advert** route:
  - Advert full
  - Advert half
  - Advert left wrap
  - Advert right wrap
  - Reset advert
- Added matching TinyMCE menu entries under Image tools.
- Stores advert layout using `data-mag-advert-layout` on inline advert figures.
- Applies advert layout consistently in the editor, A4 preview, Issue Builder preview, and measurement path.
- Keeps inline adverts captionless and excludes them from normal article-image borders.

## Testing notes

1. Insert an advert into an Article Library article.
2. Select the inserted advert and try half/left/right/full advert layout controls.
3. Refresh A4 preview and place the article fresh into Issue Builder.
