-- Hearing Tracker — initial schema
-- Safe to run again: every statement is idempotent (IF NOT EXISTS /
-- ON CONFLICT DO NOTHING guards), matching the Ledger project's own
-- migration convention.
--
-- Run in: Supabase dashboard → SQL Editor → paste this whole file → Run.

-- ──────────────────────────────────────────────────────────────────────
-- Hearings (today's live schedule + history; replaces calendar_history.json
-- and snapshot.json with real rows instead of a per-day JSON blob)
-- ──────────────────────────────────────────────────────────────────────
create table if not exists hearings (
  id          bigint generated always as identity primary key,
  date        date not null,
  chamber     text not null check (chamber in ('House', 'Senate', 'Joint')),
  committee   text not null,
  chair       text,
  time        text,            -- kept as scraped ("11:30 AM ET"), not a real timestamp
  building    text,
  room        text,
  topic       text,
  details     text,
  witnesses   jsonb not null default '[]'::jsonb,
  cancelled   boolean not null default false,
  changes     jsonb not null default '[]'::jsonb,
  link        text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  unique (date, chamber, committee, time)
);
create index if not exists hearings_date_idx on hearings (date);
create index if not exists hearings_committee_idx on hearings (committee);
-- Full-text search (roadmap idea #2): topic + committee + witness names.
alter table hearings add column if not exists search_vector tsvector
  generated always as (
    to_tsvector('english',
      coalesce(topic, '') || ' ' || coalesce(committee, '') || ' ' ||
      coalesce(details, '') || ' ' || coalesce(witnesses::text, '')
    )
  ) stored;
create index if not exists hearings_search_idx on hearings using gin (search_vector);

-- Tomorrow's forecast (build_baseline.py's role) — same shape, separate table.
create table if not exists baseline_hearings (
  id          bigint generated always as identity primary key,
  date        date not null,
  chamber     text not null check (chamber in ('House', 'Senate', 'Joint')),
  committee   text not null,
  chair       text,
  time        text,
  building    text,
  room        text,
  topic       text,
  details     text,
  witnesses   jsonb not null default '[]'::jsonb,
  cancelled   boolean not null default false,
  changes     jsonb not null default '[]'::jsonb,
  created_at  timestamptz not null default now(),
  unique (date, chamber, committee, time)
);

-- ──────────────────────────────────────────────────────────────────────
-- Members — a stable person record + their terms over time (roadmap #4)
-- ──────────────────────────────────────────────────────────────────────
create table if not exists members (
  bioguide_id text primary key,
  first_name  text,
  last_name   text,
  full_name   text not null,
  nickname    text,
  delegate    boolean not null default false,
  bio         text,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists member_terms (
  id          bigint generated always as identity primary key,
  member_id   text not null references members (bioguide_id) on delete cascade,
  chamber     text not null check (chamber in ('House', 'Senate')),
  state       text not null,
  district    text,            -- null for Senate
  party       text not null,   -- party AT THAT TIME, not necessarily current
  start_date  date not null,
  end_date    date,            -- null = currently serving
  end_reason  text,            -- 'retired' | 'lost_primary' | 'lost_general' |
                                -- 'resigned' | 'died' | 'expelled' | null
  created_at  timestamptz not null default now()
);
create index if not exists member_terms_member_idx on member_terms (member_id);
create index if not exists member_terms_seat_idx on member_terms (state, district);

create table if not exists institutional_leadership (
  bioguide_id text primary key references members (bioguide_id) on delete cascade,
  label       text not null,
  full_title  text not null,
  tier        int not null
);

create table if not exists vacant_seats (
  id         bigint generated always as identity primary key,
  state      text not null,
  district   text,
  label      text not null,
  reason     text,
  election   text,
  party      text,
  unique (state, district)
);

-- ──────────────────────────────────────────────────────────────────────
-- Votes — per-member roll-call records (roadmap #5)
-- ──────────────────────────────────────────────────────────────────────
create table if not exists votes (
  id            bigint generated always as identity primary key,
  chamber       text not null check (chamber in ('House', 'Senate')),
  congress      int not null,
  session       int not null,
  roll_number   int not null,
  vote_date     date not null,
  question      text,
  bill_number   text,
  result        text,
  yea_count     int,
  nay_count     int,
  present_count int,
  not_voting_count int,
  created_at    timestamptz not null default now(),
  unique (chamber, congress, session, roll_number)
);

create table if not exists member_votes (
  id         bigint generated always as identity primary key,
  vote_id    bigint not null references votes (id) on delete cascade,
  member_id  text not null references members (bioguide_id) on delete cascade,
  position   text not null check (position in ('Yea', 'Nay', 'Present', 'Not Voting')),
  unique (vote_id, member_id)
);
create index if not exists member_votes_member_idx on member_votes (member_id);

-- ──────────────────────────────────────────────────────────────────────
-- Subscriptions (roadmap #1) — anonymous identity, no email required.
-- user_id comes from Supabase anonymous sign-in, created silently client-side.
-- ──────────────────────────────────────────────────────────────────────
create table if not exists subscriptions (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users (id) on delete cascade,
  kind        text not null check (kind in ('committee', 'member', 'chamber', 'keyword')),
  value       text not null,
  email       text,            -- optional add-on, never required
  created_at  timestamptz not null default now(),
  unique (user_id, kind, value)
);

create table if not exists notification_log (
  id               bigint generated always as identity primary key,
  subscription_id  uuid not null references subscriptions (id) on delete cascade,
  hearing_id       bigint references hearings (id) on delete set null,
  change_summary   text not null,
  sent_at          timestamptz not null default now(),
  unique (subscription_id, hearing_id, change_summary)
);

-- ──────────────────────────────────────────────────────────────────────
-- DomeWatch-sourced data (carried over from their current JSON shapes)
-- ──────────────────────────────────────────────────────────────────────
create table if not exists domewatch_calendar (
  date        date primary key,
  labels      jsonb not null default '[]'::jsonb,
  fetched_at  timestamptz not null default now()
);

create table if not exists domewatch_whip (
  id               text primary key,
  subject          text,
  posted_at        timestamptz,
  parsed_at        timestamptz,
  publish_date     date,
  house_meets_at   text,
  first_votes      text,
  last_votes       text,
  week_ahead_text  text,
  items            jsonb not null default '[]'::jsonb,
  created_at       timestamptz not null default now()
);

create table if not exists domewatch_meeting_committees (
  meeting_id      text primary key,
  committee_name  text not null,
  last_checked_at timestamptz not null default now()
  -- Replaces scrape_meeting_committees.py's dict-insertion-order recency
  -- trick, which doesn't survive the move to a real table.
);

-- ──────────────────────────────────────────────────────────────────────
-- Row Level Security
-- ──────────────────────────────────────────────────────────────────────
alter table hearings enable row level security;
alter table baseline_hearings enable row level security;
alter table members enable row level security;
alter table member_terms enable row level security;
alter table institutional_leadership enable row level security;
alter table vacant_seats enable row level security;
alter table votes enable row level security;
alter table member_votes enable row level security;
alter table domewatch_calendar enable row level security;
alter table domewatch_whip enable row level security;
alter table domewatch_meeting_committees enable row level security;
alter table subscriptions enable row level security;
alter table notification_log enable row level security;

-- Public content: readable by anyone (including anonymous sign-ins),
-- writable only by the service_role key (which bypasses RLS entirely),
-- so no insert/update/delete policy is needed for these.
do $$
declare
  t text;
begin
  for t in select unnest(array[
    'hearings', 'baseline_hearings', 'members', 'member_terms',
    'institutional_leadership', 'vacant_seats', 'votes', 'member_votes',
    'domewatch_calendar', 'domewatch_whip', 'domewatch_meeting_committees'
  ])
  loop
    execute format(
      'drop policy if exists "public read" on %I; create policy "public read" on %I for select using (true);',
      t, t
    );
  end loop;
end $$;

-- Subscriptions/notifications: only the owning anonymous (or future email)
-- identity can see or touch their own rows.
drop policy if exists "own subscriptions" on subscriptions;
create policy "own subscriptions" on subscriptions
  for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "own notification log" on notification_log;
create policy "own notification log" on notification_log
  for select using (
    exists (
      select 1 from subscriptions s
      where s.id = notification_log.subscription_id and s.user_id = auth.uid()
    )
  );
