// Congressional Hearing Tracker — Service Worker
// Caches static assets; always fetches fresh hearing data

const CACHE_NAME = 'hearing-tracker-v1';

// Static assets to cache on install
const PRECACHE = [
  '/hearing-tracker/',
  '/hearing-tracker/index.html',
  '/hearing-tracker/members.html',
  '/hearing-tracker/offline.html',
  'https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;700&family=IBM+Plex+Sans:wght@300;400;600;700&family=Playfair+Display:wght@700&display=swap',
];

// Hearing data — always fetch fresh, fall back to cache
const NETWORK_FIRST = [
  '/hearing-tracker/hearings.json',
  '/hearing-tracker/baseline.json',
];

// ── Install: precache static assets ─────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: clear old caches ───────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(k => k !== CACHE_NAME)
          .map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch: network-first for data, cache-first for assets ────────────────────
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  const path = url.pathname;

  // Hearing data — network first, stale fallback
  if (NETWORK_FIRST.some(p => path.includes(p.replace('/hearing-tracker', '')))) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Bio pages — cache first, then network
  if (path.includes('/bios/')) {
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
    return;
  }

  // Everything else — cache first, network fallback, offline page last resort
  event.respondWith(
    caches.match(event.request)
      .then(cached => {
        if (cached) return cached;
        return fetch(event.request)
          .then(response => {
            if (response.ok) {
              const clone = response.clone();
              caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
            }
            return response;
          })
          .catch(() => caches.match('/hearing-tracker/offline.html'));
      })
  );
});
