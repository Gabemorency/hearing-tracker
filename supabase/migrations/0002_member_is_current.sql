-- Two fixes ahead of the member backfill: a flag for whether a member is
-- currently serving, and a missing uniqueness constraint on member_terms.
--
-- Why this is its own column rather than inferring from member_terms:
-- the upstream data source (unitedstates/congress-legislators) gives
-- every term a fixed, scheduled end date — even someone's current term —
-- because House/Senate terms have constitutionally fixed lengths. A term
-- being "over" by date doesn't mean the person left; they may simply have
-- a new term appended right after (re-election). Whether someone is
-- currently serving is really "are they listed in legislators-current.yaml
-- right now," which this flag records directly instead of trying to
-- derive it from end dates that don't carry that meaning.
--
-- Safe to run again.
alter table members add column if not exists is_current boolean not null default true;
create index if not exists members_is_current_idx on members (is_current);

-- member_terms had no uniqueness constraint in 0001 — without one, the
-- backfill/sync script's upserts would insert a duplicate row every time
-- it runs, instead of updating the existing term. NULL district (all
-- Senate terms) doesn't break this: Postgres treats distinct NULLs as
-- non-equal for uniqueness, which is exactly the behavior we want here —
-- two different Senate terms for the same person still differ by
-- start_date.
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'member_terms_unique_term'
  ) then
    alter table member_terms
      add constraint member_terms_unique_term
      unique (member_id, chamber, state, district, start_date);
  end if;
end $$;
