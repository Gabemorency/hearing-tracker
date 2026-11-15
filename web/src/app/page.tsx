import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import type { Hearing, InstitutionalLeadership, MemberTerm } from "@/lib/types";
import Header from "@/components/Header";
import ErrorPanel from "@/components/ErrorPanel";
import HearingCard from "@/components/HearingCard";
import MemberAvatar from "@/components/MemberAvatar";
import { currentTerm, initials, partyClass } from "@/components/MemberCard";
import { BoltIcon, CalendarGridIcon, XIcon } from "@/components/icons";

export const dynamic = "force-dynamic";

type LeaderMember = {
  bioguide_id: string;
  full_name: string;
  photo_url: string | null;
  member_terms: MemberTerm[];
};

function isoDate(d: Date) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(d);
}

function pad2(n: number) {
  return String(n).padStart(2, "0");
}

function addDays(iso: string, n: number) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d + n, 12));
  return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`;
}

function dayAbbrev(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", { timeZone: "UTC", weekday: "short" }).format(date);
}

export default async function DashboardPage() {
  const supabase = await createClient();
  const now = new Date();
  const today = isoDate(now);
  const weekEnd = addDays(today, 6);
  const activityStart = addDays(today, -7);
  const activityEnd = addDays(today, 7);
  const monthParam = today.slice(0, 7);

  const [
    { data: todayData, error: todayError },
    { data: todayLabelRow },
    { data: weekHearings },
    { data: weekLabels },
    { data: leadershipRows },
    { data: activityHearings },
  ] = await Promise.all([
    supabase
      .from("hearings")
      .select("id, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
      .eq("date", today)
      .order("time", { ascending: true }),
    supabase.from("domewatch_calendar").select("labels").eq("date", today).maybeSingle(),
    supabase.from("hearings").select("date, cancelled").gte("date", today).lte("date", weekEnd),
    supabase.from("domewatch_calendar").select("date, labels").gte("date", today).lte("date", weekEnd),
    supabase
      .from("institutional_leadership")
      .select("bioguide_id, label, full_title, tier")
      .lte("tier", 2)
      .order("tier", { ascending: true }),
    supabase
      .from("hearings")
      .select("id, date, chamber, committee, topic, cancelled, changes, updated_at")
      .gte("date", activityStart)
      .lte("date", activityEnd)
      .order("updated_at", { ascending: false })
      .limit(40),
  ]);

  const todayHearings = (todayData ?? []) as Hearing[];
  const todayLabels = (todayLabelRow?.labels ?? []) as string[];
  const nextUp = todayHearings.find((h) => !h.cancelled) ?? null;

  const weekCounts = new Map<string, number>();
  for (const row of weekHearings ?? []) {
    if (row.cancelled) continue;
    weekCounts.set(row.date, (weekCounts.get(row.date) ?? 0) + 1);
  }
  const weekLabelsByDate = new Map<string, string[]>();
  for (const row of weekLabels ?? []) {
    weekLabelsByDate.set(row.date, (row.labels ?? []) as string[]);
  }
  const weekDays = Array.from({ length: 7 }, (_, i) => addDays(today, i));

  const leadership = (leadershipRows ?? []) as InstitutionalLeadership[];
  let leaderMembers: Map<string, LeaderMember> = new Map();
  if (leadership.length > 0) {
    const { data: memberRows } = await supabase
      .from("members")
      .select("bioguide_id, full_name, photo_url, member_terms(member_id, chamber, state, district, party, start_date, end_date)")
      .in(
        "bioguide_id",
        leadership.map((l) => l.bioguide_id),
      );
    leaderMembers = new Map(((memberRows ?? []) as LeaderMember[]).map((m) => [m.bioguide_id, m]));
  }
  const leaders = leadership.map((l) => ({ ...l, member: leaderMembers.get(l.bioguide_id) ?? null }));

  const recentActivity = ((activityHearings ?? []) as Hearing[])
    .filter((h) => h.changes.length > 0)
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
    .slice(0, 5);

  return (
    <div className="page">
      <Header title="Dashboard" timestamp="Your overview of what's happening in Congress right now." />

      {todayError ? (
        <ErrorPanel message={todayError.message} />
      ) : (
        <>
          <h2 style={{ marginTop: 0 }}>Next up today</h2>
          {nextUp ? (
            <HearingCard hearing={nextUp} />
          ) : (
            <div className="panel" style={{ padding: "16px 18px" }}>
              <div className="row" style={{ border: "none", padding: 0 }}>
                {todayLabels.length > 0 ? todayLabels.join(", ") : "No hearings scheduled today."}{" "}
                <Link href="/hearings">See today&apos;s full list →</Link>
              </div>
            </div>
          )}

          <h2>This week</h2>
          <div className="dash-week-strip">
            {weekDays.map((iso) => {
              const count = weekCounts.get(iso) ?? 0;
              const labels = weekLabelsByDate.get(iso) ?? [];
              const isToday = iso === today;
              return (
                <Link
                  href={`/calendar?month=${monthParam}`}
                  key={iso}
                  className={`dash-week-day${isToday ? " dash-week-day--today" : ""}`}
                >
                  <span className="dash-week-day__label">{dayAbbrev(iso)}</span>
                  <span className="dash-week-day__num">{Number(iso.slice(8, 10))}</span>
                  {count > 0 && <span className="dash-week-day__count">{count}</span>}
                  {labels.length > 0 && <span className="dash-week-day__dot" />}
                </Link>
              );
            })}
          </div>
          <Link href="/calendar" className="dash-more-link">
            <CalendarGridIcon size={14} /> Open full calendar
          </Link>

          {leaders.length > 0 && (
            <>
              <h2>Leadership</h2>
              <div className="dash-leader-row">
                {leaders
                  .filter((l) => l.member)
                  .map((l) => {
                    const m = l.member!;
                    const term = currentTerm(m.member_terms);
                    return (
                      <Link href={`/members/${m.bioguide_id}`} key={l.bioguide_id} className="dash-leader">
                        <MemberAvatar
                          photoUrl={m.photo_url}
                          initials={initials(m.full_name)}
                          partyClass={partyClass(term?.party ?? null)}
                          name={m.full_name}
                        />
                        <div className="dash-leader__name">{m.full_name}</div>
                        <div className="dash-leader__label">{l.label}</div>
                      </Link>
                    );
                  })}
              </div>
            </>
          )}

          {recentActivity.length > 0 && (
            <>
              <h2>Recent activity</h2>
              <div className="update-timeline">
                {recentActivity.map((h) => {
                  const lastChange = h.changes[h.changes.length - 1];
                  const isCancelled = lastChange.toLowerCase().includes("cancel");
                  return (
                    <div className={`update-timeline-item${isCancelled ? " cancelled" : ""}`} key={h.id}>
                      {isCancelled ? <XIcon size={10} /> : <BoltIcon />}
                      <span>
                        <strong>{h.committee}</strong> — {lastChange}
                      </span>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
