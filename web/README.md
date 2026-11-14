# Hearing Tracker — web

Next.js app reading from Supabase, replacing the static GitHub
Pages site (see `../docs/migration-plan.md` for the full phased plan).
Scraping stays on GitHub Actions in the repo root — nothing here does any
scraping; this app only reads (and, from Phase 4 on, lets visitors manage
their own alert subscriptions).

## Status

Phase 0: scaffolded. `page.tsx` is a proof-of-life read from the
`hearings` table — expect 0 rows until Phase 2 points the scraper's write
path at Supabase instead of the current JSON files.

## Develop

```bash
npm install
cp .env.example .env.local   # fill in from Supabase → Project Settings → API
npm run dev                  # http://localhost:3000
npm run typecheck
npm run lint
```

## Deploy

Vercel project, Root Directory set to `web/`. Same two env vars as
`.env.example`, set in the Vercel project's Environment Variables.
