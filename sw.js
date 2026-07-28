// Congressional Hearing Tracker — Service Worker v2
const CACHE_NAME = 'hearing-tracker-v2';

const PRECACHE = [
  '/hearing-tracker/',
  '/hearing-tracker/index.html',
  '/hearing-tracker/members.html',
  '/hearing-tracker/calendar.html',
  '/hearing-tracker/offline.html',
];

const NETWORK_FIRST_PATTERNS = ['hearings.json', 'baseline.json'];

self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) { return cache.addAll(PRECACHE); })
      .then(function() { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys()
      .then(function(keys) {
        return Promise.all(keys.filter(function(k) { return k !== CACHE_NAME; }).map(function(k) { return caches.delete(k); }));
      })
      .then(function() { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function(event) {
  var url = event.request.url;

  // DomeWatch API — never cache, always network
  if (url.includes('domewatch.us') || url.includes('congress.gov/v3')) {
    return;
  }

  // Hearing data — network first, stale fallback
  if (NETWORK_FIRST_PATTERNS.some(function(p) { return url.includes(p); })) {
    event.respondWith(
      fetch(event.request)
        .then(function(response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
          return response;
        })
        .catch(function() { return caches.match(event.request); })
    );
    return;
  }

  // Bio pages — cache first, then network
  if (url.includes('/bios/')) {
    event.respondWith(
      caches.match(event.request).then(function(cached) {
        if (cached) return cached;
        return fetch(event.request).then(function(response) {
          var clone = response.clone();
          caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
          return response;
        });
      })
    );
    return;
  }

  // Everything else — cache first, network fallback, offline page last resort
  event.respondWith(
    caches.match(event.request).then(function(cached) {
      if (cached) return cached;
      return fetch(event.request)
        .then(function(response) {
          if (response.ok) {
            var clone = response.clone();
            caches.open(CACHE_NAME).then(function(cache) { cache.put(event.request, clone); });
          }
          return response;
        })
        .catch(function() { return caches.match('/hearing-tracker/offline.html'); });
    })
  );
});
