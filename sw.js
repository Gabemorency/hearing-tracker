// Congressional Hearing Tracker — Service Worker v4
// v2 served pages and data cache-first, so once cached, browsers never saw
// updates again until the cache was manually cleared — wrong for a site
// whose whole point is data that changes every 2 hours. Everything that can
// change (pages + data JSON) is now network-first; only bio pages (rarely
// updated) stay cache-first for speed. Bumping CACHE_NAME also forces every
// existing installation to drop its stale cache on this update.
// v4: domewatch_meeting_committees.json and domewatch_calendar.json were
// added after v3 shipped and were missing from NETWORK_FIRST_DATA, so any
// installation that had already cached them (via the catch-all cache-first
// branch) would keep serving that first-ever snapshot forever — the same
// staleness bug v3 fixed for everything else, just missed for these two.
const CACHE_NAME = 'hearing-tracker-v4';

const PRECACHE = [
  '/hearing-tracker/',
  '/hearing-tracker/index.html',
  '/hearing-tracker/members.html',
  '/hearing-tracker/calendar.html',
  '/hearing-tracker/offline.html',
];

// Exact page paths — matched with endsWith so this can't accidentally
// substring-match bio pages or anything else nested under /hearing-tracker/.
const NETWORK_FIRST_PAGES = [
  '/hearing-tracker/', '/hearing-tracker/index.html',
  '/hearing-tracker/calendar.html', '/hearing-tracker/members.html',
];

// Generated data files, refreshed every 2 hours — must never go stale.
const NETWORK_FIRST_DATA = [
  'snapshot.json', 'baseline.json', 'members.json', 'calendar_history.json',
  'domewatch_whip.json', 'domewatch_floor.json', 'domewatch_meetings.json',
  'domewatch_meeting_committees.json', 'domewatch_calendar.json',
];

function isNetworkFirst(url) {
  return NETWORK_FIRST_PAGES.some(function(p) { return url.endsWith(p); }) ||
         NETWORK_FIRST_DATA.some(function(p) { return url.endsWith(p); });
}

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

  // Pages + hearing data — network first, stale cache only as a fallback
  if (isNetworkFirst(url)) {
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
