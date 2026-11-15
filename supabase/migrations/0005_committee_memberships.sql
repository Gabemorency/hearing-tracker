-- Committee rosters (full committees and subcommittees), sourced from
-- unitedstates/congress-legislators' committee-membership-current.yaml.
-- Resynced as a full snapshot every nightly run (no stable boolean like
-- members.is_current to flip), so build_members.py deletes every row and
-- re-inserts the current roster each time rather than upserting deltas.
create table if not exists committee_memberships (
  id                bigint generated always as identity primary key,
  member_id         text not null references members (bioguide_id) on delete cascade,
  committee         text not null,   -- "Financial Services" or "Financial Services — Subcommittee on ..."
  chamber           text not null check (chamber in ('House', 'Senate', 'Joint')),
  role              text not null default 'Member',
  rank              int,
  is_full_committee boolean not null default true,
  created_at        timestamptz not null default now(),
  unique (member_id, committee)
);
create index if not exists committee_memberships_member_idx on committee_memberships (member_id);
create index if not exists committee_memberships_committee_idx on committee_memberships (committee);

alter table committee_memberships enable row level security;
drop policy if exists "public read" on committee_memberships;
create policy "public read" on committee_memberships for select using (true);
