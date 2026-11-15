-- Roll-call votes, sourced directly from each chamber's own public feed
-- (House Clerk's Electronic Voting System XML, Senate's LIS XML) rather
-- than a third-party aggregator. `votes` only ever grows — a new roll
-- call in a later congress/session lands as a new row, nothing here
-- gets deleted or resynced like committee_memberships does.
--
-- Keyed by the natural (chamber, congress, session, roll_number) tuple
-- rather than a surrogate id: member_votes needs to reference the exact
-- vote it belongs to, and upserting both tables from one scraper pass
-- without a round trip to re-fetch a generated id is much simpler if
-- there's nothing to fetch back in the first place.
--
-- Dropped first rather than `create table if not exists`: if a `votes`
-- table already exists from some earlier, unrelated attempt with a
-- different column set, "if not exists" silently no-ops and leaves the
-- wrong schema in place. Safe here because nothing has ever successfully
-- synced into these two tables — this feature is brand new.
drop table if exists member_votes;
drop table if exists votes;

create table votes (
  congress         int not null,
  session          int not null,          -- 1 or 2
  chamber          text not null check (chamber in ('House', 'Senate')),
  roll_number      int not null,
  date             date not null,
  question         text not null,          -- e.g. "On Passage", "On the Amendment"
  description      text,                   -- fuller vote description, when the feed has one
  bill_number      text,                   -- e.g. "H.R. 1234" — free text, not strictly parsed
  result           text not null,          -- "Passed", "Failed", "Agreed to", ...
  yea_count        int not null default 0,
  nay_count        int not null default 0,
  present_count    int not null default 0,
  not_voting_count int not null default 0,
  fetched_at       timestamptz not null default now(),
  primary key (chamber, congress, session, roll_number)
);
create index if not exists votes_date_idx on votes (date);

-- One row per (vote, member) — how that member voted on that roll call.
create table member_votes (
  congress    int not null,
  session     int not null,
  chamber     text not null,
  roll_number int not null,
  member_id   text not null references members (bioguide_id) on delete cascade,
  position    text not null check (position in ('Yea', 'Nay', 'Present', 'Not Voting')),
  primary key (chamber, congress, session, roll_number, member_id),
  foreign key (chamber, congress, session, roll_number)
    references votes (chamber, congress, session, roll_number) on delete cascade
);
create index if not exists member_votes_member_idx on member_votes (member_id);

alter table votes enable row level security;
drop policy if exists "public read" on votes;
create policy "public read" on votes for select using (true);

alter table member_votes enable row level security;
drop policy if exists "public read" on member_votes;
create policy "public read" on member_votes for select using (true);
