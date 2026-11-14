"use client";

import { useMemo, useState } from "react";
import type { Hearing } from "@/lib/types";
import HearingCard from "./HearingCard";
import { BoltIcon, CapitolIcon, InfoIcon, XIcon } from "./icons";

type Filter = "All" | "Senate" | "House" | "Joint" | "Updated" | "Cancelled";
const FILTERS: Filter[] = ["All", "Senate", "House", "Joint", "Updated", "Cancelled"];

export default function HearingList({ hearings }: { hearings: Hearing[] }) {
  const [filter, setFilter] = useState<Filter>("All");

  const filtered = useMemo(() => {
    if (filter === "All") return hearings;
    if (filter === "Updated") return hearings.filter((h) => h.changes.length > 0);
    if (filter === "Cancelled") return hearings.filter((h) => h.cancelled);
    return hearings.filter((h) => h.chamber === filter);
  }, [hearings, filter]);

  if (hearings.length === 0) {
    return (
      <div className="cards">
        <div className="empty empty--hero">
          <CapitolIcon size={32} className="empty__icon" />
          <div className="empty__title">No hearings today</div>
          <div className="empty__sub">Congress may be in recess or no committees are scheduled. Check back tomorrow.</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="filters">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`filter-btn${filter === f ? " active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f === "Updated" ? (
              <>
                <BoltIcon /> Updated
              </>
            ) : f === "Cancelled" ? (
              <>
                <XIcon size={9} /> Cancelled
              </>
            ) : (
              f
            )}
          </button>
        ))}
      </div>
      <div className="cards">
        <div className="count-label">
          {filtered.length} hearing{filtered.length !== 1 ? "s" : ""} — tap any card to expand
        </div>
        {filtered.length === 0 ? (
          <div className="empty">No {filter !== "All" ? filter.toLowerCase() + " " : ""}hearings found.</div>
        ) : (
          <div className="card-list">
            {filtered.map((h) => (
              <HearingCard hearing={h} key={h.id} />
            ))}
          </div>
        )}
        <div className="source-note">
          <InfoIcon /> Auto-updated every 2 hrs · docs.house.gov · senate.gov · Individual committee pages
        </div>
      </div>
    </>
  );
}
