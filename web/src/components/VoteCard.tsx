"use client";

import { useState } from "react";
import Link from "next/link";
import type { MemberVote, Vote } from "@/lib/types";
import { ChevronIcon } from "./icons";
import { voteSlug } from "@/lib/votes";

function chamberClass(chamber: string) {
  return chamber === "Senate" ? "senate" : "house";
}

function resultClass(result: string) {
  const r = result.toLowerCase();
  if (r.includes("fail") || r.includes("reject")) return "fail";
  if (r.includes("pass") || r.includes("agree") || r.includes("confirm") || r.includes("adopt")) return "pass";
  return "neutral";
}

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d, 12)),
  );
}

const POSITIONS = ["Yea", "Nay", "Present", "Not Voting"] as const;

export default function VoteCard({
  vote,
  positions,
  defaultOpen = false,
  linkToDetail = false,
  memberPosition,
}: {
  vote: Vote;
  positions: MemberVote[];
  defaultOpen?: boolean;
  linkToDetail?: boolean;
  /** When set (typically alongside linkToDetail, on a member's own voting
   * record), shows how that one member voted instead of the full tally. */
  memberPosition?: MemberVote["position"];
}) {
  const [open, setOpen] = useState(defaultOpen);
  const c = chamberClass(vote.chamber);
  const rc = resultClass(vote.result);

  const grouped: Record<string, MemberVote[]> = { Yea: [], Nay: [], Present: [], "Not Voting": [] };
  for (const p of positions) {
    grouped[p.position]?.push(p);
  }

  const header = (
    <div className="card-top" onClick={linkToDetail ? undefined : () => setOpen((o) => !o)}>
      <div className="card-left">
        <div className="card-meta">
          <span className={`tag tag-${c}`}>{vote.chamber}</span>
          <span className={`tag ${rc === "fail" ? "tag-cancelled" : rc === "pass" ? "tag-vote-pass" : "tag-updated"}`}>
            {vote.result}
          </span>
          <span className="card-time">{formatDate(vote.date)}</span>
        </div>
        <div className="card-committee">
          Roll Call {vote.roll_number}
          {vote.bill_number ? ` · ${vote.bill_number}` : ""}
        </div>
        <div className="card-topic">
          {vote.question}
          {vote.description && vote.description !== vote.question ? ` — ${vote.description}` : ""}
        </div>
      </div>
      <div className="card-right">
        {memberPosition ? (
          <span className={`tag ${memberPosition === "Yea" ? "tag-vote-pass" : memberPosition === "Nay" ? "tag-cancelled" : "tag-updated"}`}>
            {memberPosition}
          </span>
        ) : (
          <div className="vote-tally">
            <span className="vote-tally__yea">{vote.yea_count}</span>
            <span className="vote-tally__sep">–</span>
            <span className="vote-tally__nay">{vote.nay_count}</span>
          </div>
        )}
        {!linkToDetail && <ChevronIcon className="card-chevron" />}
      </div>
    </div>
  );

  const body = (
    <div className="card-body">
      <div className="card-body__inner">
        {POSITIONS.map(
          (pos) =>
            grouped[pos].length > 0 && (
              <div className="card-section" key={pos}>
                <div className={`card-section-label sl-${c}`}>
                  {pos} ({grouped[pos].length})
                </div>
                <div className="vote-roster">
                  {grouped[pos].map((mv) => (
                    <Link
                      key={mv.member_id}
                      href={`/members/${mv.member_id}`}
                      className="vote-roster__member"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {mv.members?.full_name ?? mv.member_id}
                    </Link>
                  ))}
                </div>
              </div>
            ),
        )}
        {positions.length === 0 && <div className="empty" style={{ padding: "16px 0" }}>No individual positions on file for this vote.</div>}
      </div>
    </div>
  );

  if (linkToDetail) {
    return (
      <Link href={`/votes/${voteSlug(vote)}`} className={`card chamber-${c}`}>
        {header}
      </Link>
    );
  }

  return (
    <div className={`card chamber-${c}${open ? " open" : ""}`}>
      {header}
      {body}
    </div>
  );
}
