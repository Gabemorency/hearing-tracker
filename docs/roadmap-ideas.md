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

### 3. Fix floor-vote staleness (see below for the deep dive)
- A narrow, additive Supabase Realtime + frequent-poll piece just for the
  House floor banner, layered on top of the existing 2-hour DomeWatch
  fetch rather than replacing it.

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
