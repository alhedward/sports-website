# PWA plan

The public Sports.vk2ale site is now packaged as an installable Progressive Web App.

## Included

- Web app manifest at `site/manifest.webmanifest`.
- Service worker at `site/sw.js`.
- Offline fallback page at `site/offline.html`.
- App icons under `site/icons/`.
- Optional install button in the public navigation, hidden until the browser says installation is available.

## Caching behaviour

- The static app shell is cached for fast loading and offline fallback.
- Read-only API GET requests use a network-first strategy with a cached fallback.
- Suggestion submissions remain network-only because POST requests should not be silently queued without a proper retry/outbox design.

## Admin separation

The PWA work applies to the public site only. Cognito/admin tools should stay in a separate admin microsite, for example `admin.sports.vk2ale.com`, so the public site remains clean and login-free.

## Future options

- Add push notifications for major event reminders or approved-followed sports.
- Add background sync for suggestions after a proper review queue/outbox is implemented.
- Add richer offline browsing for recently viewed sport bodies and top-player profiles.
## 0.7.15 notification modal fix

The public settings/notifications modal is now hidden with an explicit CSS rule so it cannot appear automatically on page load. Notification prompts remain user-initiated from Settings only.

