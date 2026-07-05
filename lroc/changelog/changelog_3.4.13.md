# LROC v3.4.13 — Article Caption Control Fix

Date: 2026-06-14 AEST

## Changed

- Added a visible **Caption selected image** button beside the Article Library Insert image control.
- Added double-click caption editing for selected article images/figures inside TinyMCE.
- Suppressed filename-style default captions such as `image1.jpeg` and `photo.png`.
- New image insertions no longer use the asset filename as the default caption.
- Empty captions remain editable in the Article Library editor but are hidden in rendered magazine pages.
- Preserved the v3.4.12 continuation-window rendering path and footer style.

## Notes

To caption an article image, click the image in the Article Library editor and press **Caption selected image**, or double-click the image. The browser/TinyMCE resize box and link widget are no longer the only available image controls.
