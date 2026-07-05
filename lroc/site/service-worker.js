const CACHE_VERSION = 'lroc-pwa-v3.5.13-20260705-aest';
const APP_SHELL_CACHE = `${CACHE_VERSION}-shell`;
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const APP_SHELL_URLS = [
  './',
  './index.html',
  './events.html',
  './trips.html',
  './training.html',
  './documents.html',
  './articles.html',
  './magazines.html',
  './membership.html',
  './vin-check.html',
  './vehicle-help.html',
  './historic-registration.html',
  './webmail.html',
  './members.html',
  './chat.html',
  './chime-meeting.html',
  './guest-meeting.html',
  './meeting-agenda.html',
  './maintenance-log.html',
  './expo/index.html',
  './expo/visitor-info.html',
  './expo/exhibitors.html',
  './expo/caterers.html',
  './expo/tickets.html',
  './expo/camping.html',
  './expo/sponsors.html',
  './expo/location.html',
  './expo/downloads.html',
  './expo/contact.html',
  './expo/expo.css',
  './expo/expo.js',
  './expo/manifest.json',
  './expo/content.json',
  './expo/assets/expo2026.png',
  './expo/assets/expo-icon-192.png',
  './expo/assets/expo-icon-512.png',
  './expo/assets/expo-apple-touch-icon.png',
  './about.html',
  './policies.html',
  './contact.html',
  './profile.html',
  './admin.html',
  './executive-committee.html',
  './terms.html',
  './disclaimer.html',
  './privacy.html',
  './styles.css',
  './config.js',
  './auth.js',
  './app.js',
  './assets/vendor/amazon-chime-sdk-js-3.30.0.bundle.js',
  './manifest.json',
  './offline.html',
  './favicon.ico',
  './favicon.png',
  './assets/lroc-logo.png',
  './assets/vehicle-help-icon-v2.png',
  './assets/vehicle-registration-icon.png',
  './assets/vehicle.json',
  './assets/event-data.json',
  './assets/land-rover-vin-decoder.json',
  './icons/pwa-192.png',
  './icons/pwa-512.png',
  './icons/apple-touch-icon.png'
];

const CORE_ASSET_PATHS = new Set([
  '/app.js',
  '/auth.js',
  '/config.js',
  '/styles.css',
  '/manifest.json',
  '/service-worker.js'
]);

self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const cache = await caches.open(APP_SHELL_CACHE);
    await Promise.all(APP_SHELL_URLS.map(async url => {
      try {
        const response = await fetch(new Request(url, { cache: 'reload' }));
        if (response && response.ok) await cache.put(url, response.clone());
      } catch {}
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => ![APP_SHELL_CACHE, STATIC_CACHE].includes(key)).map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('message', event => {
  if (event.data?.type === 'LROC_SKIP_WAITING') self.skipWaiting();
});

function isHttpGet(request) {
  return request.method === 'GET' && request.url.startsWith('http');
}

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function isNavigationRequest(request) {
  return request.mode === 'navigate';
}

function isStaticAsset(url) {
  return /\.(?:css|js|png|jpg|jpeg|gif|svg|ico|webp|woff2?|ttf)$/i.test(url.pathname);
}

function isCoreAsset(url) {
  return CORE_ASSET_PATHS.has(url.pathname);
}

function isCacheableDocument(url) {
  return url.pathname.endsWith('.html') || url.pathname === '/' || url.pathname === '';
}

function shouldBypass(url) {
  return /\/member\//.test(url.pathname) ||
    /\/admin\//.test(url.pathname) ||
    /content\.json$/i.test(url.pathname) ||
    /articles\/index\.json$/i.test(url.pathname) ||
    /event-data\.json$/i.test(url.pathname) ||
    /\/api\//.test(url.pathname);
}

async function networkFirst(request, fallbackUrl = './offline.html') {
  const cache = await caches.open(APP_SHELL_CACHE);
  try {
    const response = await fetch(request, { cache: 'no-store' });
    if (response && response.ok && isSameOrigin(new URL(request.url))) {
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  } catch {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    const fallback = await cache.match(fallbackUrl, { ignoreSearch: true });
    return fallback || Response.error();
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cached = await cache.match(request, { ignoreSearch: true });
  const fetchPromise = fetch(request)
    .then(response => {
      if (response && response.ok) cache.put(request, response.clone()).catch(() => {});
      return response;
    })
    .catch(() => null);
  if (cached) {
    fetchPromise.catch(() => null);
    return cached;
  }
  const response = await fetchPromise;
  return response || Response.error();
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (!isHttpGet(request)) return;
  const url = new URL(request.url);
  if (!isSameOrigin(url)) return;
  if (shouldBypass(url)) return;

  if (isNavigationRequest(request) || isCacheableDocument(url) || isCoreAsset(url)) {
    event.respondWith(networkFirst(request));
    return;
  }

  if (isStaticAsset(url)) {
    event.respondWith(staleWhileRevalidate(request));
  }
});


self.addEventListener('push', event => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch { payload = { body: event.data ? event.data.text() : '' }; }
  const title = payload.title || 'LROC';
  const options = {
    body: payload.body || '',
    data: payload.data || {},
    tag: payload.tag || 'lroc-notification',
    badge: './icons/pwa-192.png',
    icon: './icons/pwa-192.png'
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url) || './chat.html';
  event.waitUntil((async () => {
    const allClients = await clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of allClients) {
      if ('focus' in client) {
        try {
          const url = new URL(client.url);
          if (url.origin === self.location.origin) {
            if ('navigate' in client) await client.navigate(targetUrl);
            return client.focus();
          }
        } catch {}
      }
    }
    if (clients.openWindow) return clients.openWindow(targetUrl);
  })());
});
