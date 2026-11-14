# Migrate to Next.js + Supabase + Vercel (Ledger-style), then build the roadmap

Approved plan. Supersedes the "full migration ... not recommended" note in
`docs/roadmap-ideas.md`, which was right for "bolt a backend onto the
static site" but not for "rebuild it, styled like a specific app you've
already shipped." Everything below is additive-first: the current GitHub
Pages site keeps running, untouched, until the new app is at parity and
there's explicit sign-off to cut over.

## Context

Target look/feel: `Gabemorency/Ledger` — Next.js (App Router) + TypeScript
on Vercel, Supabase Postgres + Row Level Security, a plain-CSS
custom-property design system (not Tailwind), a PWA service worker, Vitest
for logic, Playwright for screen-regression. Plus four of the five
features in `docs/roadmap-ideas.md` actually built: saved alerts,
full-text search across years, member history, and per-member vote
records. The fifth (live floor-vote fix) is **deferred** — see Phase 4.

## Facts confirmed before approval

- **Ledger's real stack** (cloned and read): Next.js 16 + React 19 + TS,
  `@supabase/ssr`/`supabase-js`, Vitest, Playwright, plain CSS with
  `:root` custom properties + `@media (prefers-color-scheme)` +
  `data-theme` override — same light/dark mechanism this repo's
  `theme.css` already uses. Local-first sync (change lands on-device,
  then uploads; offline queue). Demo mode when Supabase env is absent.
- **`calendar_history.json` has no retention limit** — accumulating
  unbounded (69+ days observed), not capped at ~90 days as
  `docs/roadmap-ideas.md` assumed. More history to backfill than expected;
  no TTL logic to replicate.
- **Vercel Hobby plan cron is daily-only** (confirmed via Vercel's docs —
  sub-daily schedules fail at deploy time; Pro allows per-minute). This is
  why any frequent poller belongs on GitHub Actions, not Vercel Cron.
- **Supabase free tier**: 500MB Postgres, 200 concurrent Realtime
  connections, 2M Realtime messages/month, project pauses after 7 days
  idle (restorable; a non-issue once live and written to regularly). All
  data here is small text/metadata; photos stay hotlinked, never stored.
- **No email login, ever.** Supabase anonymous sign-in gives every visitor
  a real identity silently in the background, no account UI, the moment
  they pick something to follow. Email is an optional add-on surfaced
  later, never a gate.
- **Floor-vote fix deferred.** Of the five roadmap ideas, it rests on the
  shakiest ground — DomeWatch's rate limits for faster polling aren't
  documented, and even on GitHub Actions it's realistically ~5-minute
  polling, not true instant push. Still improves on today's 2 hours, but
  lowest-confidence of the five, and nothing else depends on it. Revisit
  after the rest is live: test DomeWatch's tolerance for faster polling
  cautiously, add the poller + Realtime push then if it holds up.

## Target architecture

- **New Next.js app lives in this same repo**, at `web/`. One source of
  truth, same PR/CI conventions already established. Vercel project
  configured with Root Directory = `web/`.
- **Scraping stays on GitHub Actions.** Playwright/headless-browser
  automation doesn't fit Vercel serverless function limits. Existing
  workflows keep their schedules; only their *write target* changes
  (Supabase instead of `git commit`).
- **Supabase**: Postgres for all data (Realtime reserved for if/when the
  deferred floor-vote push gets built). RLS only matters on user-owned
  tables (`subscriptions`, `notification_log`) — hearings/members/votes
  stay public-read.
- **Design system**: port `theme.css`'s existing tokens (gold/senate/
  house/joint accents, light/dark via the same pattern) into a
  Ledger-style `globals.css` — same token mechanism, this site's own
  colors, same restrained card/panel visual language (mobile-first,
  soft rounded panels, tabular-nums for numbers/times).
- **PWA**: port `sw.js`'s instant-load-app-shell / stale-while-revalidate
  pattern.

## Data model (Supabase Postgres)

Derived from the real JSON shapes in the current pipeline:

- `hearings` — one row per hearing (chamber, committee, chair, time,
  building, room, topic, details, witnesses jsonb, cancelled, changes
  jsonb, date), from `snapshot.json`'s shape. Replaces
  `calendar_history.json`'s per-day blob with real rows — this is what
  makes full-text search and "today" the same table.
- `members` (bioguide_id PK) + `member_terms` (chamber, state, district,
  party-at-the-time, start/end date, how it ended) — from `members.json`,
  backfilled from `legislators-historical.yaml`.
- `institutional_leadership`, `vacant_seats` — carried over from their
  current JSON shape; `validate_hardcoded.py`'s auto-fix logic becomes a
  scheduled check against these tables instead of files.
- `votes` (roll call metadata) + `member_votes` (member_id, vote_id,
  position) — new tables, fed by a new GitHub Actions scraper pulling
  Clerk of the House / Senate LIS roll-call data.
- `subscriptions`, `notification_log` — RLS per-user (anonymous identity).
- `domewatch_calendar`, `domewatch_whip`, `domewatch_meeting_committees` —
  carried over from current shapes; `scrape_meeting_committees.py`'s
  cache-recency trick (dict insertion order) becomes an explicit
  `last_checked_at` column.
- `baseline_hearings` — same shape as `hearings`, keeps
  `build_baseline.py`'s tomorrow-forecast/merge-source role intact.
- `floor_status` — not built now; schema reserved for when/if the
  deferred floor-vote fix gets picked up.

## Phased build (each phase has its own verification gate; no phase
touches the live domain)

**Phase 0 — Scaffold + backfill.**
- ✅ Done: Supabase project created, `supabase/migrations/0001_init.sql`
  run successfully (13 tables + RLS confirmed in Table Editor).
- ✅ Done: `web/` scaffolded (Next.js 16.4.6 + TS), GitHub repo secrets
  (`SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY`) added
  for the future scraper write path.
- ✅ Done: Vercel project connected (Root Directory `web/`, env vars
  `NEXT_PUBLIC_SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_ANON_KEY` set as Config
  type on Production + Preview). Live and verified end to end — the
  deployed proof-of-life page correctly reads the empty `hearings` table
  through RLS and shows the expected "no hearings yet" state.
  (Note for next time this comes up: the Supabase dashboard's "Project
  URL" field is sometimes copied including a `/rest/v1/` suffix from a
  different part of the UI — the env var must be just
  `https://<ref>.supabase.co`, nothing appended, or the Supabase client's
  own path-building breaks with "Invalid path specified in request URL.")
- ⏳ Remaining: one-time Python backfill scripts (reuse existing parsing
  logic, change only the output target) to load `members.json`,
  `calendar_history.json` (all accumulated days), `legislators-historical.yaml`,
  `institutional_leadership.json`, `vacant_seats.json` into Supabase.
- **Verify** (once backfill is written): query row counts match source
  file counts; spot-check a few known hearings/members against the old
  JSON.

**Phase 1 — Port reads.** Next.js pages for today's hearings, calendar,
member directory, member profile — reading Supabase, styled in the new
system. Deployed to a Vercel preview URL only. Service worker ported.
- **Verify**: side-by-side against the live GitHub Pages site; screen-
  regression baseline (Ledger's `e2e/snapshot.mjs` pattern) established.

**Phase 2 — Port writes.** Modify the write step in `scrape.py`,
`bio_sync.py`, `record_calendar_day.py`, etc. (logic unchanged, output
target changed) to upsert into Supabase via the service-role key. Keep
committing JSON in parallel for a validation window, then drop it once
confident.
- **Verify**: dispatch each real workflow, confirm Supabase rows match
  what the old JSON-commit path would have produced.

**Phase 3 — Cutover.** Point the real domain at the Vercel app. Only after
explicit approval, given this is a live public site. Old GitHub Pages path
kept as fallback briefly, then retired.

**Phase 4 — Build the roadmap features**, now that the foundation exists:
1. Member history pages (data already backfilled in Phase 0 — mostly UI)
2. Full-text search (`tsvector` over the now-durable `hearings` table)
3. Saved alerts + subscriptions (anonymous sign-in, no email required —
   pick a committee, follow it, done; Web Push via the ported service
   worker, the `changes` field already computed by the scraper; email as
   an optional add-on later)
4. Per-member vote records (new Clerk/Senate LIS scraper → `votes`/
   `member_votes`, surfaced on member profiles)

**Deferred**: live floor-vote fix (see "Facts confirmed" above).

## Verification approach overall

Real tests (`pytest` for Python, `vitest`/`next typecheck` for the new
app), real workflow dispatches with log inspection before calling any
phase done, standard PR → CI → merge for every change. Cutover specifically
waits for explicit go-ahead rather than happening automatically.

## Open items still to resolve (not blocking Phase 0)

- DomeWatch's rate limits/ToS for more-frequent polling aren't publicly
  documented — relevant only when the deferred floor-vote fix is revisited.
- Web Push needs a VAPID key / push setup decision when Phase 4 reaches
  alerts — not needed until then.
