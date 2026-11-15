"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import type { Hearing } from "@/lib/types";
import HearingCard from "./HearingCard";
import { ChevronIcon, CapitolIcon } from "./icons";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function labelKind(label: string): "cancelled" | "holiday" | "default" {
  const l = label.toLowerCase();
  if (l.includes("cancel")) return "cancelled";
  if (l.includes("holiday")) return "holiday";
  return "default";
}

function dayLabel(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "UTC",
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(date);
}

export default function CalendarGrid({
  year,
  month,
  cells,
  hearings,
  labelsByDate,
  todayIso,
  prevMonth,
  nextMonth,
  monthLabel,
}: {
  year: number;
  month: number;
  cells: string[];
  hearings: Hearing[];
  labelsByDate: Record<string, string[]>;
  todayIso: string;
  prevMonth: string;
  nextMonth: string;
  monthLabel: string;
}) {
  const todayInView = cells.includes(todayIso) && Number(todayIso.slice(5, 7)) === month;
  const [selected, setSelected] = useState<string | null>(todayInView ? todayIso : null);

  const hearingsByDate = useMemo(() => {
    const m = new Map<string, Hearing[]>();
    for (const h of hearings) {
      const key = h.date ?? "unknown";
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(h);
    }
    return m;
  }, [hearings]);

  const selectedHearings = selected ? (hearingsByDate.get(selected) ?? []) : [];
  const selectedLabels = selected ? (labelsByDate[selected] ?? []) : [];

  return (
    <>
      <div className="cal-grid-nav">
        <Link href={`/calendar?month=${prevMonth}`} className="cal-grid-nav__btn" aria-label="Previous month">
          <ChevronIcon size={14} className="cal-grid-nav__chevron cal-grid-nav__chevron--prev" />
        </Link>
        <h2 className="cal-grid-nav__title">{monthLabel}</h2>
        <Link href={`/calendar?month=${nextMonth}`} className="cal-grid-nav__btn" aria-label="Next month">
          <ChevronIcon size={14} className="cal-grid-nav__chevron cal-grid-nav__chevron--next" />
        </Link>
      </div>

      <div className="cal-grid-weekdays">
        {WEEKDAYS.map((w) => (
          <div key={w} className="cal-grid-weekday">
            {w}
          </div>
        ))}
      </div>

      <div className="cal-grid">
        {cells.map((iso) => {
          const inMonth = Number(iso.slice(5, 7)) === month && Number(iso.slice(0, 4)) === year;
          const dayNum = Number(iso.slice(8, 10));
          const dayHearings = hearingsByDate.get(iso) ?? [];
          const labels = labelsByDate[iso] ?? [];
          const isToday = iso === todayIso;
          const isSelected = iso === selected;
          return (
            <button
              key={iso}
              className={[
                "cal-cell",
                inMonth ? "" : "cal-cell--outside",
                isToday ? "cal-cell--today" : "",
                isSelected ? "cal-cell--selected" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={() => setSelected(iso)}
            >
              <span className="cal-cell__num">{dayNum}</span>
              {dayHearings.length > 0 && <span className="cal-cell__count">{dayHearings.length}</span>}
              {labels.length > 0 && (
                <span className="cal-cell__dots">
                  {labels.slice(0, 3).map((l, i) => (
                    <span key={i} className={`cal-cell__dot cal-cell__dot--${labelKind(l)}`} />
                  ))}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="cal-detail">
        {!selected ? (
          <div className="empty">Tap a day above to see its hearings.</div>
        ) : (
          <>
            <div className="calendar-day-header">
              <div className="calendar-day-title">
                {dayLabel(selected)}
                {selected === todayIso ? " · Today" : ""}
                {selectedLabels.length > 0 && (
                  <span className="calendar-day-labels">
                    {selectedLabels.map((l) => (
                      <span className="calendar-label-pill" key={l}>
                        {l}
                      </span>
                    ))}
                  </span>
                )}
              </div>
              <div className="calendar-day-count">
                {selectedHearings.length} hearing{selectedHearings.length !== 1 ? "s" : ""}
              </div>
            </div>
            {selectedHearings.length > 0 ? (
              <div className="card-list">
                {selectedHearings.map((h) => (
                  <HearingCard hearing={h} key={h.id} />
                ))}
              </div>
            ) : (
              <div className="empty empty--hero">
                <CapitolIcon size={28} className="empty__icon" />
                <div className="empty__title">No hearings recorded</div>
                <div className="empty__sub">Nothing scheduled or recorded for this date.</div>
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
