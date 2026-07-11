// DomeWatch live floor data
// API key injected at build time
(function () {
  var KEY = 'dw_bmB0cl-PcW4xZ4E9NhHddqK8uol1o7Ua';
  var BASE = 'https://data.domewatch.us/v1';
  var etag = '';

  if (!KEY || KEY === 'dw_bmB0cl-PcW4xZ4E9NhHddqK8uol1o7Ua') return;

  function fmt(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
  }

  // Floor status bar
  function updateBar(d) {
    var bar = document.getElementById('floor-bar');
    var txt = document.getElementById('floor-bar__text');
    var vot = document.getElementById('floor-bar__vote');
    var tim = document.getElementById('floor-bar__time');
    if (!bar) return;
    bar.className = 'floor-bar';
    if (!d) { bar.classList.add('floor-bar--loading'); return; }
    vot.style.display = 'none';
    if (d.inSession) {
      if (d.vote && d.vote.rollCall) {
        bar.classList.add('floor-bar--vote-active');
        txt.textContent = 'House In Session \u2014 Vote: ' + (d.vote.question || 'Roll Call');
        var c = d.vote.counts || {};
        vot.textContent = 'D ' + ((c.D || {}).yea || 0) + '  R ' + ((c.R || {}).yea || 0);
        vot.style.display = 'inline';
      } else {
        bar.classList.add('floor-bar--in-session');
        txt.textContent = 'House In Session' + (d.currentActivity ? ' \u2014 ' + d.currentActivity : '');
      }
    } else {
      bar.classList.add('floor-bar--recess');
      txt.textContent = d.currentActivity || 'House Not In Session';
    }
    if (tim) tim.textContent = 'Updated ' + fmt(d.asOf || new Date().toISOString());
  }

  function pollFloor() {
    var h = { 'X-API-Key': KEY };
    if (etag) h['If-None-Match'] = etag;
    fetch(BASE + '/floor', { headers: h })
      .then(function (r) {
        if (r.status === 304) return null;
        if (!r.ok) return null;
        var e = r.headers.get('ETag');
        if (e) etag = e;
        return r.json();
      })
      .then(function (d) { if (d) updateBar(d); })
      .catch(function () {});
  }

  // Whip notices
  function loadWhip() {
    fetch(BASE + '/whip-notices?limit=1', { headers: { 'X-API-Key': KEY } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.data || !data.data.length) return;
        var n = data.data[0];
        var sec = document.getElementById('whip-section');
        var met = document.getElementById('whip-meta');
        var itm = document.getElementById('whip-items');
        if (!sec) return;
        var mh = '';
        if (n.houseMeetsAt) mh += '<span>House meets: ' + n.houseMeetsAt + '</span>';
        if (n.firstVotes)   mh += '<span>First votes: ' + n.firstVotes + '</span>';
        if (n.lastVotes)    mh += '<span>Last votes: ' + n.lastVotes + '</span>';
        met.innerHTML = mh;
        var bh = '';
        (n.items || []).filter(function (b) { return b.confidence !== 'low'; }).forEach(function (b) {
          var rc = b.recommendation ? 'wrec wrec-' + b.recommendation : '';
          bh += '<div class="whip-item">';
          if (b.billUrl) {
            bh += '<a href="' + b.billUrl + '" target="_blank" rel="noopener" class="whip-item__bill">' + (b.billNumber || '') + '</a>';
          } else {
            bh += '<span class="whip-item__bill">' + (b.billNumber || '') + '</span>';
          }
          if (b.title) bh += '<div class="whip-item__title">' + b.title + '</div>';
          bh += '<div class="whip-item__meta">';
          if (rc) bh += '<span class="' + rc + '">' + (b.recommendation || '').replace('_', ' ') + '</span>';
          if (b.position) bh += '<span>' + b.position + '</span>';
          bh += '</div></div>';
        });
        itm.innerHTML = bh || '<p>No upcoming vote items.</p>';
        sec.style.display = 'block';
      })
      .catch(function () {});
  }

  // Floor updates
  function loadUpdates() {
    fetch(BASE + '/floor-updates?limit=5', { headers: { 'X-API-Key': KEY } })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.data || !data.data.length) return;
        var sec = document.getElementById('floor-updates-section');
        var lst = document.getElementById('floor-updates-list');
        if (!sec) return;
        var h = '';
        data.data.forEach(function (u) {
          h += '<div class="floor-update">';
          h += '<div class="floor-update__subject">' + (u.subject || 'Floor Update') + '</div>';
          if (u.bodyText) h += '<div class="floor-update__body">' + u.bodyText + '</div>';
          h += '<div class="floor-update__time">' + fmt(u.publishedAt) + '</div>';
          h += '</div>';
        });
        lst.innerHTML = h;
        sec.style.display = 'block';
      })
      .catch(function () {});
  }

  document.addEventListener('DOMContentLoaded', function () {
    pollFloor();
    loadWhip();
    loadUpdates();
    setInterval(pollFloor, 30000);
  });
}());
