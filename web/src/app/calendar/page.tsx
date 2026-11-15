import { createClient } from "@/lib/supabase/server";
import type { Hearing } from "@/lib/types";
import Header from "@/components/Header";
import CalendarGrid from "@/components/CalendarGrid";
import ErrorPanel from "@/components/ErrorPanel";

export const dynamic = "force-dynamic";

function isoDate(d: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d);
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

// Always 42 cells (6 full Sun-Sat weeks) so every month renders the same
// grid height — a 5-week month next to a 6-week month would otherwise
// jump height on every month navigation.
function buildMonthGrid(year: number, month: number) {
  const firstWeekday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const start = new Date(Date.UTC(year, month - 1, 1 - firstWeekday, 12));
  const cells: string[] = [];
  for (let i = 0; i < 42; i++) {
    const d = new Date(start);
    d.setUTCDate(d.getUTCDate() + i);
    cells.push(`${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())}`);
  }
  return cells;
}

function shiftMonth(year: number, month: number, delta: number) {
  const base = new Date(Date.UTC(year, month - 1 + delta, 1));
  return `${base.getUTCFullYear()}-${pad2(base.getUTCMonth() + 1)}`;
}

export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ month?: string }>;
}) {
  const { month: monthParam } = await searchParams;
  const supabase = await createClient();
  const now = new Date();
  const todayIso = isoDate(now);
  const [todayY, todayM] = todayIso.split("-").map(Number);

  let year = todayY;
  let month = todayM;
  if (monthParam && /^\d{4}-\d{2}$/.test(monthParam)) {
    const [y, m] = monthParam.split("-").map(Number);
    if (m >= 1 && m <= 12) {
      year = y;
      month = m;
    }
  }

  const cells = buildMonthGrid(year, month);
  const gridStart = cells[0];
  const gridEnd = cells[cells.length - 1];

  const [{ data, error }, { data: domewatchDays }] = await Promise.all([
    supabase
      .from("hearings")
      .select(
        "id, date, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link",
      )
      .gte("date", gridStart)
      .lte("date", gridEnd)
      .order("date", { ascending: true })
      .order("time", { ascending: true }),
    supabase.from("domewatch_calendar").select("date, labels").gte("date", gridStart).lte("date", gridEnd),
  ]);

  const hearings = (data ?? []) as Hearing[];
  const labelsByDate: Record<string, string[]> = {};
  for (const row of domewatchDays ?? []) {
    labelsByDate[row.date] = (row.labels ?? []) as string[];
  }

  const monthLabel = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric", timeZone: "UTC" }).format(
    new Date(Date.UTC(year, month - 1, 15, 12)),
  );

  return (
    <div className="page">
      <Header title="Hearing Calendar" timestamp="Tap any day to see what's scheduled." />
      {error ? (
        <ErrorPanel message={error.message} />
      ) : (
        <CalendarGrid
          year={year}
          month={month}
          cells={cells}
          hearings={hearings}
          labelsByDate={labelsByDate}
          todayIso={todayIso}
          prevMonth={shiftMonth(year, month, -1)}
          nextMonth={shiftMonth(year, month, 1)}
          monthLabel={monthLabel}
        />
      )}
    </div>
  );
}
