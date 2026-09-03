const CACHE_NAME = 'kisanprocure-v1';
const STATIC_ASSETS = [
  '/',
  '/offline',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css',
  'https://cdn.jsdelivr.net/npm/chart.js'
];

// Install Event: Cache Static Assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Pre-caching warning:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate Event: Clean Old Caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch Event: Serve from Cache or Network, with Offline Fallback
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // CRITICAL SECURITY RULE: NEVER cache API requests (/api/...) or non-GET requests
  if (url.pathname.startsWith('/api/') || request.method !== 'GET') {
    return; // Pass through to network directly
  }

  event.respondWith(
    caches.match(request).then((cachedResponse) => {
      if (cachedResponse) {
        // Return cached asset, fetch update in background (stale-while-revalidate for static assets)
        fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            caches.open(CACHE_NAME).then((cache) => cache.put(request, networkResponse));
          }
        }).catch(() => {/* Offline silent fallback */});

        return cachedResponse;
      }

      return fetch(request).catch(() => {
        // If HTML page request fails and offline, return /offline fallback page
        if (request.headers.get('accept') && request.headers.get('accept').includes('text/html')) {
          return caches.match('/offline');
        }
      });
    })
  );
});
