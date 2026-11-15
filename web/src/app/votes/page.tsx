import { createPublicClient } from "@/lib/supabase/public";
import type { MemberVote, Vote } from "@/lib/types";
import Header from "@/components/Header";
import ErrorPanel from "@/components/ErrorPanel";
import SourceNote from "@/components/SourceNote";
import VoteDirectory from "@/components/VoteDirectory";
import { voteSlug } from "@/lib/votes";

// Cached for 1 minute (ISR) — votes.yml syncs every 2 hours, but this
// stays short so a just-triggered manual sync shows up quickly too.
export const revalidate = 60;

const VOTE_FIELDS =
  "congress, session, chamber, roll_number, date, question, description, bill_number, result, yea_count, nay_count, present_count, not_voting_count";

export default async function VotesPage() {
  const supabase = createPublicClient();

  const { data: voteRows, error } = await supabase
    .from("votes")
    .select(VOTE_FIELDS)
    .order("date", { ascending: false })
    .order("roll_number", { ascending: false })
    .limit(40);

  if (error) {
    return (
      <div className="page">
        <Header title="Votes" timestamp="" />
        <ErrorPanel message={error.message} />
      </div>
    );
  }

  const votes = (voteRows ?? []) as Vote[];

  // Roll numbers reset every session, so a bare "roll_number IN (...)"
  // filter could pull in positions from an unrelated vote in an older
  // session that happens to share the same number — group by the full
  // (chamber, congress, session) tuple before filtering, not just chamber.
  const groups = new Map<string, { chamber: string; congress: number; session: number; rolls: number[] }>();
  for (const v of votes) {
    const key = `${v.chamber}-${v.congress}-${v.session}`;
    const g = groups.get(key) ?? { chamber: v.chamber, congress: v.congress, session: v.session, rolls: [] };
    g.rolls.push(v.roll_number);
    groups.set(key, g);
  }

  const positionResults = await Promise.all(
    [...groups.values()].map((g) =>
      supabase
        .from("member_votes")
        .select("congress, session, chamber, roll_number, member_id, position, members(full_name, bioguide_id)")
        .eq("chamber", g.chamber)
        .eq("congress", g.congress)
        .eq("session", g.session)
        .in("roll_number", g.rolls),
    ),
  );

  const positionsByVote: Record<string, MemberVote[]> = {};
  for (const { data } of positionResults) {
    for (const mv of (data ?? []) as unknown as MemberVote[]) {
      const key = voteSlug(mv);
      (positionsByVote[key] ??= []).push(mv);
    }
  }

  return (
    <div className="page">
      <Header title="Votes" timestamp="Recent roll call votes · House and Senate" />
      <VoteDirectory votes={votes} positionsByVote={positionsByVote} />
      <SourceNote>Vote data: House Clerk Electronic Voting System · Senate LIS</SourceNote>
    </div>
  );
}
