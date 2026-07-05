# v3.5.13 — Issue Composer Page Item Foundation

- Added an Issue Composer page-item/region foundation view so the editor can inspect what is physically on each magazine page before article flow is considered.
- Added page item inventory cards for layout/content panels, including kind labels for adverts, generated blocks, article flow, filler, images/photos, notices/text and locked panels.
- Added an A4 mini-map in Composer showing placed page items and detected free regions for the selected page.
- Added a first free-space preflight readout that explains fixed pages, whole-page locks, locked page items and available article-flow regions.
- Added item-level Lock/Unlock controls in Composer. These save `panelLocked` on the selected page item while preserving the existing page, layout slot and content slot data.
- Added an issue page strip showing fixed, blank, mixed and locked pages so bitty mixed layouts are visible from the normal Composer workflow.
- Exposed `window.mag3513Composer` helpers for future placement/planner work.
- Kept Advanced Layout unchanged as the manual workshop path.
