# Roadmap ideas (brainstorm, not committed to)

Captured from a conversation about whether/how to add a backend (Vercel +
Supabase) alongside the existing static GitHub Pages + GitHub Actions site.
Nothing here is scheduled — this is a holding pen for ideas worth coming
back to.

## Context

The current site is fully static: GitHub Actions scrapes on a schedule and
commits regenerated HTML/JSON straight to the repo. That's a good fit for
public, read-only, periodically-refreshed content, and should **stay** the
foundation. A backend (Supabase Postgres + Vercel) would be additive, not a
replacement — only for capabilities a static site structurally can't do.

## Priority ideas (user confirmed interest)

### 1. Saved alerts + committee/member subscriptions
- User follows committees, members, chambers, or keywords.
- Scraper already computes a `changes` field (new hearing, cancellation,
  witnesses added, time/room moved) — that's the trigger, it just has
  nowhere to go today.
- Needs: `users` (Supabase Auth), `subscriptions` table, `notification_log`
  (dedupe), and one new step at the end of the existing scrape pipeline
  that matches changes against subscriptions and fires a notification.
- Delivery: the site already has a service worker (added for offline bio
  caching) — Web Push can piggyback on that with no email provider needed.
  Email (immediate or digest) as a fallback/preference.
- Scraping itself doesn't change at all; this only adds a step after it.

### 2. Full-text search across years
- `calendar_history.json` only keeps ~90 days today; no durable history.
- Fix: keep every scraped hearing permanently in a Supabase table instead
  of overwriting a rolling snapshot.
- Postgres full-text search (`tsvector`) over topic/committee/witness
  fields — no separate search service needed.
- Side benefit: cheap aggregate queries for free (hearings per committee
  per month, etc.) once the data lives in a real table.

### 3. Fix floor-vote staleness
- A narrow, additive Supabase Realtime + frequent-poll piece just for the
  House floor banner, layered on top of the existing 2-hour DomeWatch
  fetch rather than replacing it (not a replacement for the 2-hour scrape).
- Caveat to check before building: ~1-minute polling is a ~100x increase
  in call volume to DomeWatch vs. today's 2-hour cadence — need to confirm
  their rate limits/ToS tolerate that, even gated to likely session windows.

### 4. Member history database (bios, photos, join/leave over time)
- Already solved today: photos (via `unitedstates/images`, keyed by
  `bioguide_id`, no hosting needed), current bios, and automatic add/remove
  of members as they join/leave (`bio_sync.py`, every 6h).
- The gap: departed members are just deleted from `bios_hardcoded.json` —
  no history kept. Can't answer "who held this seat before," "this
  member's full career," or "who left this term and why."
- Model: `members` (stable person record, bioguide_id as key) +
  `member_terms` (chamber, state, district, party *at that time*, start/end
  date, how the term ended). Party-at-the-time matters because of
  switching.
- `unitedstates/congress-legislators` also publishes
  `legislators-historical.yaml` — decades of past membership back to 1789 —
  so this can be backfilled in one import, not built up from scratch.
- Note: doesn't strictly need Supabase. Historical terms don't change once
  over, so this could ship as static pages too. Fits the backend better if
  built alongside the rest, but isn't blocked on it.

### 5. Per-member vote records ("who voted what on what")
- New data source, not an extension of an existing one: DomeWatch only
  gives aggregate tallies for the *current* floor vote, not who voted
  which way, and not history. Per-member roll-call data comes from the
  Clerk of the House / Senate LIS XML feeds instead.
- Granularity decision made: stop at **per-member vote records attached to
  member profiles** ("Sen. X — recent votes"), linking out to the bill on
  congress.gov rather than mirroring its full text/status/cosponsors.
  Going further (full bill tracking, voting-alignment analytics) is a
  different product — GovTrack/ProPublica Represent already do that well,
  and it's a lot of ongoing maintenance surface for something that isn't
  this site's core identity.
- General granularity rule this sets for the app: stay deep on hearings
  (the core), go wide-but-shallow on adjacent context (members, votes) —
  enough to be useful, not enough to become a second app.

## Other ideas from the same conversation

- **iCal export per subscription** — personalized `.ics` feed of hearings
  for followed committees, so they show up in Google/Outlook automatically.
- **"My committees" dashboard** — logged-in homepage filtered to just what
  you follow instead of the full list.
- **Public hearing change history** — timeline per hearing ("time moved
  10am→2pm," "witness added") using the `changes` data that's already
  computed but currently only shown as the latest state.
- **Public read API** — Supabase auto-generates REST/GraphQL over the
  data; not really offerable from JSON files that get overwritten every
  2 hours.
- **Internal pipeline health dashboard** — one page showing scraper
  anomalies (unmatched committees, "Off-site" buildings, witness-fetch
  failures) instead of grepping Action logs.
- **Committee rosters over time** — which members sat on which committee
  when, not just who chaired it (already tracked). Reuses `member_terms`
  directly; connects hearing data to who was actually on the committee at
  the time.
- **"This witness has testified before" cross-referencing** — a free
  byproduct of the full-text-search work: witness names are already
  extracted per hearing, so once history is durable, link a name to their
  past appearances automatically.
- **Weekly digest email** — "here's what's coming up for your followed
  committees," a lower-frequency complement to instant alerts. Same
  subscriptions infrastructure, different cadence/UX.
- **CSV export of search results / a member's vote history** — cheap
  add-on once search and votes exist; serves researchers/journalists
  without needing the full public-API build.

## Explicitly deprioritized

- **User accounts on their own** — not useful in isolation; only worth
  building as the login layer the alerts feature needs.
- **Admin UI for hardcoded data** (chairs, link selectors, etc.) — git PRs
  already give review + a full audit trail for free, and these edits are
  infrequent. Low value for the added auth/form/write-path surface.
- **Full migration off GitHub Pages/Actions onto Vercel/Supabase** — not
  recommended. The static+cron architecture is well-matched to this app's
  actual needs; a full rewrite adds real operational complexity (DB to
  manage, two more services' secrets/auth, real cost once off free tiers)
  without a corresponding benefit. Any backend work should be additive,
  not a replacement.
