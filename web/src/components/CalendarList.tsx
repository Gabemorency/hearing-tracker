"use client";

import { useMemo, useState } from "react";
import type { Hearing } from "@/lib/types";
import HearingCard from "./HearingCard";
import { BoltIcon, XIcon } from "./icons";

type Filter = "All" | "Senate" | "House" | "Joint" | "Updated" | "Cancelled";
const FILTERS: Filter[] = ["All", "Senate", "House", "Joint", "Updated", "Cancelled"];

function dayLabel(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(date);
}

export default function CalendarList({
  hearings,
  todayIso,
  labelsByDate = {},
}: {
  hearings: Hearing[];
  todayIso: string;
  labelsByDate?: Record<string, string[]>;
}) {
  const [filter, setFilter] = useState<Filter>("All");

  const filtered = useMemo(() => {
    if (filter === "All") return hearings;
    if (filter === "Updated") return hearings.filter((h) => h.changes.length > 0);
    if (filter === "Cancelled") return hearings.filter((h) => h.cancelled);
    return hearings.filter((h) => h.chamber === filter);
  }, [hearings, filter]);

  const byDate = useMemo(() => {
    const m = new Map<string, Hearing[]>();
    for (const h of filtered) {
      const key = h.date ?? "unknown";
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(h);
    }
    return m;
  }, [filtered]);
  const dates = useMemo(
    () => [...new Set([...byDate.keys(), ...Object.keys(labelsByDate)])].sort(),
    [byDate, labelsByDate],
  );

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
      {dates.length === 0 ? (
        <div className="empty">No {filter !== "All" ? filter.toLowerCase() + " " : ""}hearings in this window.</div>
      ) : (
        dates.map((date) => {
          const dayHearings = byDate.get(date) ?? [];
          const labels = labelsByDate[date] ?? [];
          return (
            <div className="calendar-day" key={date}>
              <div className="calendar-day-header">
                <div className="calendar-day-title">
                  {dayLabel(date)}
                  {date === todayIso ? " · Today" : ""}
                  {labels.length > 0 && (
                    <span className="calendar-day-labels">
                      {labels.map((l) => (
                        <span className="calendar-label-pill" key={l}>
                          {l}
                        </span>
                      ))}
                    </span>
                  )}
                </div>
                <div className="calendar-day-count">
                  {dayHearings.length} hearing{dayHearings.length !== 1 ? "s" : ""}
                </div>
              </div>
              {dayHearings.length > 0 ? (
                <div className="card-list">
                  {dayHearings.map((h) => (
                    <HearingCard hearing={h} key={h.id} />
                  ))}
                </div>
              ) : (
                <div className="empty" style={{ padding: "14px 0", textAlign: "left" }}>
                  No hearings recorded for this date.
                </div>
              )}
            </div>
          );
        })
      )}
    </>
  );
}
