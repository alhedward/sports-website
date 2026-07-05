# LROC v3.4.36 — Deploy Helper Auto-Refresh Picker

AEST: 2026-06-17 17:47

## Changed
- Updated `lroc/deployer/deploy_helper.py` to v1.14.
- Latest package picker now auto-refreshes the selected folder every 2 seconds.
- Newly arrived packages appear without pressing Refresh.
- Existing selected package is preserved where possible; a new newest package is highlighted but not deployed until selected.
