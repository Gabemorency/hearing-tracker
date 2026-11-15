"use client";

import { useState } from "react";
import type { Hearing } from "@/lib/types";
import HearingCard from "./HearingCard";

type WeekDay = {
  iso: string;
  dayLabel: string;
  dayNum: number;
  isToday: boolean;
  count: number;
  hasLabel: boolean;
  hearings: Hearing[];
};

export default function DashboardWeekStrip({ days }: { days: WeekDay[] }) {
  const defaultOpen = days.find((d) => d.isToday)?.iso ?? null;
  const [openIso, setOpenIso] = useState<string | null>(defaultOpen);
  const openDay = days.find((d) => d.iso === openIso) ?? null;

  return (
    <>
      <div className="dash-week-strip">
        {days.map((d) => (
          <button
            key={d.iso}
            className={`dash-week-day${d.isToday ? " dash-week-day--today" : ""}${d.iso === openIso ? " dash-week-day--open" : ""}`}
            onClick={() => setOpenIso((cur) => (cur === d.iso ? null : d.iso))}
            aria-expanded={d.iso === openIso}
          >
            <span className="dash-week-day__label">{d.dayLabel}</span>
            <span className="dash-week-day__num">{d.dayNum}</span>
            {d.count > 0 && <span className="dash-week-day__count">{d.count}</span>}
            {d.hasLabel && <span className="dash-week-day__dot" />}
          </button>
        ))}
      </div>
      <div className={`dash-week-detail${openDay ? " dash-week-detail--open" : ""}`}>
        <div className="dash-week-detail__inner">
          {openDay && (
            <div className="card-list" style={{ paddingTop: 10 }}>
              {openDay.hearings.length === 0 ? (
                <div className="empty" style={{ padding: "20px 0" }}>
                  No hearings recorded for this day.
                </div>
              ) : (
                openDay.hearings.map((h) => <HearingCard hearing={h} key={h.id} />)
              )}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
