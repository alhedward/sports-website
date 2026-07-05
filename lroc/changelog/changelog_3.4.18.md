# Changelog v3.4.18 — A4 Preview Refresh Wiring

Timestamp: 2026-06-15 20:01:27 AEST

## Changed
- Fixed the Article Library **Refresh A4 preview** control so it uses delegated click handling and survives UI re-renders.
- The refresh now visibly clears/rebuilds the preview panel and updates the Article Library editor status with a timestamp.
- The preview refresh explicitly synchronises TinyMCE content before rebuilding the local A4 preview.
- Clarified in the UI that the refresh is local and does not require a network request.

## Preserved
- Caption double-click/control behaviour from v3.4.13.
- Manual image earlier/later flow controls.
- v3.4.17 preview alignment renderer path.
- LROC footer style in Issue Builder.
