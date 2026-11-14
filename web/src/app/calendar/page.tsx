import { createClient } from "@/lib/supabase/server";
import type { Hearing } from "@/lib/types";
import Header from "@/components/Header";
import HearingCard from "@/components/HearingCard";
import { CapitolIcon } from "@/components/icons";

export const dynamic = "force-dynamic";

const DAYS_BACK = 7;
const DAYS_FORWARD = 7;

function isoDate(d: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d);
}

function dayLabel(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "long", month: "long", day: "numeric" }).format(date);
}

export default async function CalendarPage() {
  const supabase = await createClient();
  const now = new Date();
  const start = new Date(now);
  start.setDate(start.getDate() - DAYS_BACK);
  const end = new Date(now);
  end.setDate(end.getDate() + DAYS_FORWARD);

  const startIso = isoDate(start);
  const endIso = isoDate(end);
  const todayIso = isoDate(now);

  const { data, error } = await supabase
    .from("hearings")
    .select("id, date, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
    .gte("date", startIso)
    .lte("date", endIso)
    .order("date", { ascending: true })
    .order("time", { ascending: true });

  const hearings = (data ?? []) as Hearing[];
  const byDate = new Map<string, Hearing[]>();
  for (const h of hearings) {
    const key = h.date ?? "unknown";
    if (!byDate.has(key)) byDate.set(key, []);
    byDate.get(key)!.push(h);
  }
  const dates = [...byDate.keys()].sort();

  return (
    <div className="page">
      <Header
        title="Hearing Calendar"
        timestamp={`${DAYS_BACK} days back · ${DAYS_FORWARD} days ahead · America/New_York`}
      />
      {error ? (
        <div className="panel" style={{ marginTop: 18 }}>
          <div className="row" style={{ color: "var(--text-dim)" }}>
            Couldn&apos;t reach Supabase: {error.message}
          </div>
        </div>
      ) : dates.length === 0 ? (
        <div className="cards">
          <div className="empty empty--hero">
            <CapitolIcon size={32} className="empty__icon" />
            <div className="empty__title">No hearings in this window</div>
            <div className="empty__sub">
              Nothing scheduled or recorded for {startIso} through {endIso} yet.
            </div>
          </div>
        </div>
      ) : (
        dates.map((date) => (
          <div className="calendar-day" key={date}>
            <div className="calendar-day-header">
              <div className="calendar-day-title">
                {dayLabel(date)}
                {date === todayIso ? " · Today" : ""}
              </div>
              <div className="calendar-day-count">
                {byDate.get(date)!.length} hearing{byDate.get(date)!.length !== 1 ? "s" : ""}
              </div>
            </div>
            <div className="card-list">
              {byDate.get(date)!.map((h) => (
                <HearingCard hearing={h} key={h.id} />
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
