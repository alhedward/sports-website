# LROC v3.4.8 — Deployer helper integration

Timestamp: 2026-06-14 14:32:55 AEST

## Added

- Added `lroc/deployer/deploy_helper.py`, the verbose GitHub Actions deployment helper.
- Added `lroc/deployer/file.deploy.txt` as a deploy-script reference/template for the helper workflow.
- Added `lroc/deployer/README.md` with local requirements and usage notes.

## Changed

- Updated the package root `lroc/file.deploy.txt` so future package deploys stage `lroc/deployer` as part of the repo commit.
- Updated `VERSION` to `3.4.8`.
- Updated service-worker cache namespace to `v3.4.8`.

## Notes

- No article renderer logic was intentionally changed in this package.
- Renderer work remains focused on eliminating avoidable white space on non-final generated article pages.
