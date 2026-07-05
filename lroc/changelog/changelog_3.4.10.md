# Changelog v3.4.10 — Article Renderer Column Reset

Timestamp: 2026-06-14 15:29:03 AEST

## Why this release exists

v3.4.7 and v3.4.9 attempted to reduce white space by destructively splitting article HTML into manual blocks and explicit columns. That made the result worse in two ways:

- list markers/bullets could disappear because original lists were split into artificial one-item list fragments;
- whitespace could become worse because the manual block packer could not faithfully match the browser's native column layout.

## Changes

- Replaced destructive explicit-column page fragments with a windowed native CSS multi-column sheet.
- Each generated issue page now keeps the original TinyMCE article HTML intact and clips a different page-width window from the same flowed article sheet.
- Restored native `<ul>` / `<ol>` rendering so bullet markers are not lost by list splitting.
- Added image max-height control inside the article renderer window so oversized images are reduced before they cause large blank page areas.
- Retained the existing LROC footer style.
- Kept deployer integration from v3.4.8.

## Notes

This is a reset of the article body flow strategy, not a cosmetic trim pass. The goal is to get back to predictable article flow before adding smarter image-position controls.
