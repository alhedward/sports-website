# v3.5.0 — Region-Based Placement Foundation

- Starts replacing page/slot-type assumptions with occupied/vacant region handling.
- Generated TinyMCE article continuation pages now preserve existing placed content as regions instead of inheriting stale page-wide layout state.
- Article generated slots now store the region kind/basis used for placement diagnostics.
- Adds shared `mag350IssueRegions` helpers for occupied-region and vacant-region inspection.
- Keeps the TinyMCE A4 composer direction and excludes the abandoned Layout Lab/GrapesJS branch.

Future work:
- Use the region helpers as the authority for preflight placement planning.
- Flow TinyMCE article content across multiple differently sized vacant regions, rather than only page windows.
- Move locking toward content/region locks instead of page-wide locks except for covers/finalised pages.
- Add future A3 printer/imposition PDF planning.
