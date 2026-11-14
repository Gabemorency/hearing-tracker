import { createClient } from "@/lib/supabase/server";
import type { Hearing } from "@/lib/types";
import Header from "@/components/Header";
import CalendarList from "@/components/CalendarList";
import { CapitolIcon } from "@/components/icons";

export const dynamic = "force-dynamic";

const DAYS_BACK = 7;
const DAYS_FORWARD = 7;

function isoDate(d: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d);
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

  const [{ data, error }, { data: domewatchDays }] = await Promise.all([
    supabase
      .from("hearings")
      .select("id, date, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
      .gte("date", startIso)
      .lte("date", endIso)
      .order("date", { ascending: true })
      .order("time", { ascending: true }),
    supabase.from("domewatch_calendar").select("date, labels").gte("date", startIso).lte("date", endIso),
  ]);

  const hearings = (data ?? []) as Hearing[];
  const labelsByDate: Record<string, string[]> = {};
  for (const row of domewatchDays ?? []) {
    labelsByDate[row.date] = (row.labels ?? []) as string[];
  }
  const hasDomewatchContext = Object.keys(labelsByDate).length > 0;

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
      ) : hearings.length === 0 && !hasDomewatchContext ? (
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
        <CalendarList hearings={hearings} todayIso={todayIso} labelsByDate={labelsByDate} />
      )}
    </div>
  );
}
