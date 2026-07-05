# v3.5.12 — Trips Map Geocoding Fallback and Config Repair

- Trips & Events admin map search now handles a missing Geoapify geocoding key gracefully instead of reporting it as a failed location lookup.
- Backend geocode route now returns a configured=false response with a useful message when address search is not configured.
- Admin Open/Search in maps link now works from meeting name/address even before latitude/longitude are known.
- Terraform now reuses the Geoapify map tile key for geocoding when a separate geocoding key is not supplied.
- Added GEOAPIFY_GEOCODING_URL to the Lambda environment so the existing Terraform variable is honoured.
- Updated Terraform example/docs wording to show the geocoding key is optional when the map tile key is present.
