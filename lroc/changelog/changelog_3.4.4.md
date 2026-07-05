# Changelog — v3.4.4

Date: 2026-06-14 10:41 AEST

## Article Renderer Page Preservation / Header Suppression Fix

- Fixed TinyMCE article continuation pages losing their generated page fragments when a generated page was opened in the Issue Builder editor and saved again.
  - `articlePageHtml` is now preserved through the dynamic slot-definition path.
  - TinyMCE page metadata is now carried through editor reads/writes, including page index/count, dimensions, diagnostics and column count.
  - Preview recovery can repaginate from the stored full article HTML when an older v3.4.3 page is missing its `articlePageHtml` fragment.
- Suppressed the external Article Library slot title above generated `mce_article_page` previews.
  - The rendered TinyMCE article HTML owns headings and titles.
  - Continuation pages no longer repeat the Article Library title/header at the top of every page.
- Treated whitespace-only headline/page-header overrides as blank.
  - Entering a single space no longer creates a real override or accidental blank header.
- Added a CSS safety rule to hide stale slot-editor `<h4>` headers above rendered TinyMCE article pages.
- Improved page-bottom fill slightly by:
  - splitting plain text paragraphs into smaller sentence-aware chunks
  - moving the soft/full pagination thresholds closer to the actual measured page capacity
- Updated the renderer diagnostics version to `3.4.4`.
- Updated the magazine editor status/roadmap copy for v3.4.4.
- Updated the service-worker cache namespace for v3.4.4.

## Preserved

- v3.4.3 continuation-page placement
- v3.4.3 two-column measurement fix
- v3.4.2 controlled magazine blocks
- v3.4.2 image caption controls
- manual page breaks
- locked page/panel preservation
- multiple-of-four issue expansion behaviour
- Article Library direct placement workflow
- package-provided `file.deploy.txt` deployment flow
