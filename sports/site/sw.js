const APP_VERSION = '0.7.21-primaryadmin-device-approval';
const STATIC_CACHE = `sports-vk2ale-static-${APP_VERSION}`;
const API_CACHE = `sports-vk2ale-api-${APP_VERSION}`;

const APP_SHELL = [
  '/',
  '/index.html',
  '/offline.html',
  '/styles.css',
  '/app.js',
  '/config.js',
  '/manifest.webmanifest',
  '/sponsors.json',
  '/admin/',
  '/admin/index.html',
  '/admin/admin.css',
  '/admin/admin.js',
  '/admin/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/maskable-512.png',
  '/icons/apple-touch-icon.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => cache.addAll(APP_SHELL.map(url => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  const expected = new Set([STATIC_CACHE, API_CACHE]);
  event.waitUntil(
    caches.keys()
      .then(names => Promise.all(names.map(name => expected.has(name) ? null : caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  const cache = await caches.open(STATIC_CACHE);
  cache.put(request, response.clone());
  return response;
}

async function networkFirst(request) {
  const cache = await caches.open(API_CACHE);
  try {
    const response = await fetch(request);
    if (response && (response.ok || response.type === 'opaque')) {
      cache.put(request, response.clone()).catch(() => {});
    }
    return response;
  } catch (_err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    throw _err;
  }
}

self.addEventListener('fetch', event => {
  const request = event.request;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (request.mode === 'navigate') {
    const isAdminPath = url.pathname === '/admin' || url.pathname.startsWith('/admin/');
    const cacheKey = isAdminPath ? '/admin/index.html' : '/index.html';
    const fallbackPage = isAdminPath ? '/admin/index.html' : '/offline.html';
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(STATIC_CACHE).then(cache => cache.put(cacheKey, copy)).catch(() => {});
          return response;
        })
        .catch(() => caches.match(fallbackPage))
    );
    return;
  }

  if (url.origin === self.location.origin) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // Never cache authenticated admin API calls or any request that carries an
  // Authorization header. These responses are user-specific and should not be
  // replayed from the service worker cache after logout or account changes.
  if (url.pathname.startsWith('/admin') || request.headers.has('Authorization')) {
    event.respondWith(fetch(request));
    return;
  }

  // Cross-origin public API reads can be kept network-first, with a cached
  // fallback for basic browsing when the network drops out.
  event.respondWith(networkFirst(request));
});


self.addEventListener('push', event => {
  let payload = { title: 'Sports.vk2ale', body: 'There is an update.', url: '/' };
  try {
    if (event.data) payload = { ...payload, ...event.data.json() };
  } catch (_err) {}
  event.waitUntil(self.registration.showNotification(payload.title, {
    body: payload.body,
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    data: { url: payload.url || '/' }
  }));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url ? event.notification.data.url : '/';
  event.waitUntil(clients.openWindow(url));
});
