import { notFound } from "next/navigation";
import Link from "next/link";
import { createPublicClient } from "@/lib/supabase/public";
import type { MemberVote, Vote } from "@/lib/types";
import Header from "@/components/Header";
import ErrorPanel from "@/components/ErrorPanel";
import SourceNote from "@/components/SourceNote";
import VoteCard from "@/components/VoteCard";

// Cached for 5 minutes per vote (ISR) — a vote's roster doesn't change
// once the roll call closes. Pages are generated on demand per slug.
export const revalidate = 300;

function parseSlug(slug: string) {
  const match = slug.match(/^(house|senate)-(\d+)-(\d+)-(\d+)$/);
  if (!match) return null;
  const [, chamber, congress, session, roll] = match;
  return {
    chamber: chamber === "senate" ? "Senate" : "House",
    congress: Number(congress),
    session: Number(session),
    roll_number: Number(roll),
  };
}

export default async function VoteDetailPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const key = parseSlug(slug);
  if (!key) notFound();

  const supabase = createPublicClient();

  const [{ data: vote, error }, { data: positions }] = await Promise.all([
    supabase
      .from("votes")
      .select(
        "congress, session, chamber, roll_number, date, question, description, bill_number, result, yea_count, nay_count, present_count, not_voting_count",
      )
      .eq("chamber", key.chamber)
      .eq("congress", key.congress)
      .eq("session", key.session)
      .eq("roll_number", key.roll_number)
      .maybeSingle(),
    supabase
      .from("member_votes")
      .select("congress, session, chamber, roll_number, member_id, position, members(full_name, bioguide_id)")
      .eq("chamber", key.chamber)
      .eq("congress", key.congress)
      .eq("session", key.session)
      .eq("roll_number", key.roll_number),
  ]);

  if (error) {
    return (
      <div className="page">
        <Header title="Vote" timestamp="" />
        <ErrorPanel message={error.message} />
      </div>
    );
  }
  if (!vote) notFound();

  return (
    <div className="page">
      <Header title={`${key.chamber} Roll Call ${key.roll_number}`} timestamp={`Congress ${key.congress}, Session ${key.session}`} />
      <Link href="/votes" className="back-link">
        ← All votes
      </Link>
      <div className="card-list" style={{ marginTop: 14 }}>
        <VoteCard vote={vote as Vote} positions={(positions ?? []) as unknown as MemberVote[]} defaultOpen />
      </div>
      <SourceNote>Vote data: House Clerk Electronic Voting System · Senate LIS</SourceNote>
    </div>
  );
}
