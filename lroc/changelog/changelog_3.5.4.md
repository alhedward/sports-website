# LROC v3.5.4 — TinyMCE A4 Composer Containment Fix

Date: 2026-06-19 17:39 AEST

## Changed

- Stopped the TinyMCE A4 composer grey background from expanding endlessly.
- Removed TinyMCE autoresize from the Article Library editor path.
- The white A4 working surface now sits inside a fixed editor viewport.
- The editor remains A4-like while A4 preview remains the confirmation render.

## Notes

This is a containment repair for v3.5.3. It does not yet implement stacked multi-page editing shells; it prevents the runaway outer editor growth first.
