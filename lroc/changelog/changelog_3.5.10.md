# v3.5.10 — Issue Composer Workflow Layer

- Added a new editor-facing Issue Composer tab.
- Reframed magazine production around the simpler content-first workflow:
  1. generate known club pages,
  2. carry forward/place adverts,
  3. place edited articles,
  4. fill remaining gaps,
  5. run final polish/review.
- Demoted the old Issue Builder tab to Advanced Layout so the slot/page-item machinery stays available but is no longer presented as the normal workflow.
- Added composer status cards for pages, generated pages, advert pages/panels, article pages, blank interiors and locked items.
- Added composer action buttons that jump to the relevant tools/pages without making the editor choose low-level slot methods first.
- Open Issue now lands on Issue Composer instead of Issue Detail.
- Updated article placement wording to “Place article with composer”.
- Softened legacy/manual placement language so it is clearly an exception path.
- No backend placement semantics were changed in this pass; existing article, advert, generated-page and advanced layout machinery is preserved underneath.
