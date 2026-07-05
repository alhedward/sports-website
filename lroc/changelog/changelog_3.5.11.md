# v3.5.11 — Event Calendar Month Selection and Save Repair

- Renamed the editor-facing event-calendar template wording from “next four months” to selected-month language while preserving the existing template ID for compatibility. Client-side template normalisation also covers older/stale bootstrap template names.
- Increased event calendar month selection support from 1–12 months to 1–24 months in the UI and backend sanitiser.
- Updated the event-calendar editor help text so the editor chooses months, refreshes from club events, reviews descriptions, then saves the page layout.
- Calendar refresh now preserves existing edited short descriptions for events that remain in the refreshed range.
- Changing the calendar month count now refreshes the calendar snapshot from club events and queues an autosave.
- Fixed a likely event-calendar save blocker: failure to write edited blurbs back to the live event records no longer prevents the magazine page layout from saving.
- Added calendar slot ID alias handling so existing saved calendar pages using `calendar` and newer pages using `event_calendar` can still be edited through the current template controls.
