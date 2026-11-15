"use client";

import { useMemo, useState } from "react";
import type { MemberVote, Vote } from "@/lib/types";
import VoteCard from "./VoteCard";
import { voteSlug } from "@/lib/votes";
import { CapitolIcon } from "./icons";

type ChamberFilter = "All" | "House" | "Senate";

export default function VoteDirectory({ votes, positionsByVote }: { votes: Vote[]; positionsByVote: Record<string, MemberVote[]> }) {
  const [chamber, setChamber] = useState<ChamberFilter>("All");

  const filtered = useMemo(
    () => (chamber === "All" ? votes : votes.filter((v) => v.chamber === chamber)),
    [votes, chamber],
  );

  if (votes.length === 0) {
    return (
      <div className="cards">
        <div className="empty empty--hero">
          <CapitolIcon size={32} className="empty__icon" />
          <div className="empty__title">No votes recorded yet</div>
          <div className="empty__sub">Roll call votes sync a few times a day while Congress is in session.</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="chip-row">
        {(["All", "House", "Senate"] as const).map((c) => (
          <button key={c} className={`chip${chamber === c ? " active" : ""}`} onClick={() => setChamber(c)}>
            {c === "All" ? "All votes" : c}
          </button>
        ))}
      </div>
      <div className="count-label">
        {filtered.length} recent vote{filtered.length !== 1 ? "s" : ""}
      </div>
      {filtered.length === 0 ? (
        <div className="empty">No votes match that filter.</div>
      ) : (
        <div className="card-list">
          {filtered.map((v) => (
            <VoteCard vote={v} positions={positionsByVote[voteSlug(v)] ?? []} key={voteSlug(v)} />
          ))}
        </div>
      )}
    </>
  );
}
