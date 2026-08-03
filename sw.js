// Congressional Hearing Tracker — Service Worker v6
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
// v5: added theme.css (the shared design-token stylesheet every page now
// links) to PRECACHE — without it, an offline visitor's first-ever page
// load would render entirely unstyled.
// v6: plain cache-first for bio pages had the same staleness bug v3 fixed
// for everything else — a factual correction (e.g. a stale "former
// President" reference) never reached a browser that had already cached
// that page, and the only way out was a manual CACHE_NAME bump each time,
// which doesn't scale and is easy to forget. Bio pages now use stale-
// while-revalidate instead: still serve the cached copy instantly (same
// speed as before), but always re-fetch in the background and update the
// cache for next time. The fix a visitor is currently missing is one page
// load behind, permanently, without anyone needing to touch this file
// again — this version bump is the last one bio content fixes will ever
// need. Also wrapped every background cache.put() in the file (not just
// the new one) in event.waitUntil() — without it, the browser is free to
// kill the worker as soon as the response is sent, before an un-awaited
// cache write finishes, which would silently drop the very update this
// fix depends on.
const CACHE_NAME = 'hearing-tracker-v6';

const PRECACHE = [
  '/hearing-tracker/',
  '/hearing-tracker/index.html',
  '/hearing-tracker/members.html',
  '/hearing-tracker/calendar.html',
  '/hearing-tracker/offline.html',
  '/hearing-tracker/theme.css',
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
          event.waitUntil(caches.open(CACHE_NAME).then(function(cache) { return cache.put(event.request, clone); }));
          return response;
        })
        .catch(function() { return caches.match(event.request); })
    );
    return;
  }

  // Bio pages — stale-while-revalidate: return the cached copy immediately
  // if there is one (same instant load as pure cache-first), but always
  // kick off a network fetch in parallel and overwrite the cache with
  // whatever comes back. That fetch isn't awaited before responding, so it
  // can't slow this load down — its only job is making sure the *next*
  // load of this page is current, indefinitely, with no version bump ever
  // required just because a bio's text changed.
  if (url.includes('/bios/')) {
    event.respondWith(
      caches.open(CACHE_NAME).then(function(cache) {
        return cache.match(event.request).then(function(cached) {
          var refresh = fetch(event.request).then(function(response) {
            if (response.ok) cache.put(event.request, response.clone());
            return response;
          }).catch(function() { return cached; });
          // The cache write has to survive after this handler returns its
          // response — without waitUntil() keeping the worker alive for
          // it, the browser is free to kill the worker the moment
          // `cached` is sent back, and the background refresh (and the
          // whole point of it) could be silently dropped.
          event.waitUntil(refresh);
          return cached || refresh;
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
            event.waitUntil(caches.open(CACHE_NAME).then(function(cache) { return cache.put(event.request, clone); }));
          }
          return response;
        })
        .catch(function() { return caches.match('/hearing-tracker/offline.html'); });
    })
  );
});
