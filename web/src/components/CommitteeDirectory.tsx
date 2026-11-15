"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { CapitolIcon, ChevronIcon, SearchIcon } from "./icons";

export type CommitteeMemberRow = {
  bioguide_id: string;
  full_name: string;
  role: string;
  rank: number | null;
};

export type CommitteeGroup = {
  committee: string;
  chamber: "House" | "Senate" | "Joint";
  members: CommitteeMemberRow[];
};

type ChamberFilter = "All" | "House" | "Senate" | "Joint";

function roleTagClass(role: string) {
  const r = role.toLowerCase();
  if (r.includes("chair") && !r.includes("ranking")) return "tag tag-senate";
  if (r.includes("ranking")) return "tag tag-cancelled";
  return "";
}

export default function CommitteeDirectory({ committees }: { committees: CommitteeGroup[] }) {
  const [query, setQuery] = useState("");
  const [chamber, setChamber] = useState<ChamberFilter>("All");
  const [open, setOpen] = useState<Set<string>>(new Set());

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return committees.filter((c) => {
      if (chamber !== "All" && c.chamber !== chamber) return false;
      if (q && !c.committee.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [committees, query, chamber]);

  function toggle(name: string) {
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }

  if (committees.length === 0) {
    return (
      <div className="cards">
        <div className="empty empty--hero">
          <CapitolIcon size={32} className="empty__icon" />
          <div className="empty__title">No committee data yet</div>
          <div className="empty__sub">Committee rosters haven&apos;t been synced into Supabase yet.</div>
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
          placeholder="Search committees…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search committees"
        />
      </div>
      <div className="chip-row">
        {(["All", "House", "Senate", "Joint"] as const).map((c) => (
          <button key={c} className={`chip${chamber === c ? " active" : ""}`} onClick={() => setChamber(c)}>
            {c}
          </button>
        ))}
      </div>
      <div className="count-label">
        {filtered.length} committee{filtered.length !== 1 ? "s" : ""}
      </div>
      {filtered.length === 0 ? (
        <div className="empty">No committees match that search.</div>
      ) : (
        <div className="card-list">
          {filtered.map((c) => {
            const isOpen = open.has(c.committee);
            return (
              <div
                className={`card chamber-${c.chamber.toLowerCase()}${isOpen ? " open" : ""}`}
                key={c.committee}
                onClick={() => toggle(c.committee)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    toggle(c.committee);
                  }
                }}
              >
                <div className="card-top">
                  <div className="card-left">
                    <div className="card-meta">
                      <span className={`tag tag-${c.chamber.toLowerCase()}`}>{c.chamber}</span>
                    </div>
                    <div className="card-committee">{c.committee}</div>
                    <div className="card-topic">
                      {c.members.length} member{c.members.length !== 1 ? "s" : ""}
                    </div>
                  </div>
                </div>
                <ChevronIcon className="card-chevron" />
                {isOpen && (
                  <div className="committee-roster">
                    {c.members.map((m) => (
                      <Link
                        href={`/members/${m.bioguide_id}`}
                        className="committee-roster-item"
                        key={m.bioguide_id}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <span className="committee-roster-item__name">{m.full_name}</span>
                        {m.role !== "Member" && <span className={roleTagClass(m.role)}>{m.role}</span>}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
