# LROC v3.4.20 — Advert caption suppression

Date: 2026-06-15 AEST

## Changed
- Insert Advert in the Article Library TinyMCE editor now inserts advert artwork as an inline advert figure without a caption.
- Existing inline advert figures are normalised to remove any figcaption content rather than showing an advert title or filename.
- Caption selected image now refuses to caption inline advert figures and cleans any accidental advert figcaption.
- Added render/editor CSS safeguards to hide figcaptions on inline advert figures in Article Library preview, Issue Builder preview, and measurement paths.

## Preserved
- Normal article image caption behaviour from v3.4.13 remains unchanged.
- Manual image earlier/later flow controls remain unchanged.
- A4 preview / meaningful-page trim logic from v3.4.19 remains unchanged.
