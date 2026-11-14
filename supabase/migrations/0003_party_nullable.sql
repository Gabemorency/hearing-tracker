-- member_terms.party was NOT NULL in 0001, but real historical data
-- breaks that assumption: some First Congress (1789) terms genuinely
-- have no party on record, since organized political parties as we know
-- them didn't fully exist yet. Discovered by actually running the
-- backfill against real data, not by the dry run (which checked shape,
-- not database constraints).
--
-- Safe to run again.
alter table member_terms alter column party drop not null;
