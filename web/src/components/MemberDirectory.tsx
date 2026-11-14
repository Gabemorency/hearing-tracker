"use client";

import { useMemo, useState } from "react";
import type { InstitutionalLeadership, Member } from "@/lib/types";
import MemberCard, { currentTerm } from "./MemberCard";
import { CapitolIcon, SearchIcon } from "./icons";

type ChamberFilter = "All" | "House" | "Senate";
type PartyFilter = "All" | "D" | "R" | "I";

export default function MemberDirectory({
  members,
  leadership,
}: {
  members: Member[];
  leadership: InstitutionalLeadership[];
}) {
  const [query, setQuery] = useState("");
  const [chamber, setChamber] = useState<ChamberFilter>("All");
  const [party, setParty] = useState<PartyFilter>("All");

  const leadershipMap = useMemo(
    () => new Map(leadership.map((l) => [l.bioguide_id, l])),
    [leadership],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return members.filter((m) => {
      const term = currentTerm(m.member_terms);
      if (chamber !== "All" && term?.chamber !== chamber) return false;
      if (party !== "All" && term?.party?.[0]?.toUpperCase() !== party) return false;
      if (q && !m.full_name.toLowerCase().includes(q) && !term?.state?.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [members, query, chamber, party]);

  if (members.length === 0) {
    return (
      <div className="cards">
        <div className="empty empty--hero">
          <CapitolIcon size={32} className="empty__icon" />
          <div className="empty__title">No member data yet</div>
          <div className="empty__sub">The member directory hasn&apos;t been synced into Supabase yet.</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="search-row">
        <SearchIcon />
        <input
          className="search-input"
          placeholder="Search by name or state…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search members"
        />
      </div>
      <div className="chip-row">
        {(["All", "House", "Senate"] as const).map((c) => (
          <button key={c} className={`chip${chamber === c ? " active" : ""}`} onClick={() => setChamber(c)}>
            {c}
          </button>
        ))}
        <span style={{ width: 1, background: "var(--border)", margin: "0 2px" }} />
        {(["All", "D", "R", "I"] as const).map((p) => (
          <button key={p} className={`chip${party === p ? " active" : ""}`} onClick={() => setParty(p)}>
            {p === "All" ? "All parties" : p}
          </button>
        ))}
      </div>
      <div className="count-label">
        {filtered.length} member{filtered.length !== 1 ? "s" : ""}
      </div>
      {filtered.length === 0 ? (
        <div className="empty">No members match that search.</div>
      ) : (
        <div className="member-grid">
          {filtered.map((m) => (
            <MemberCard member={m} leadership={leadershipMap.get(m.bioguide_id)} key={m.bioguide_id} />
          ))}
        </div>
      )}
    </>
  );
}
