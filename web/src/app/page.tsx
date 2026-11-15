import Link from "next/link";
import { createPublicClient } from "@/lib/supabase/public";
import type { Hearing, InstitutionalLeadership, MemberTerm, Vote } from "@/lib/types";
import Header from "@/components/Header";
import ErrorPanel from "@/components/ErrorPanel";
import HearingCard from "@/components/HearingCard";
import MemberAvatar from "@/components/MemberAvatar";
import DashboardWeekStrip from "@/components/DashboardWeekStrip";
import { voteSlug } from "@/lib/votes";
import { currentTerm, initials, partyClass } from "@/components/MemberCard";
import { BoltIcon, CalendarGridIcon, ChevronIcon, VoteIcon, XIcon } from "@/components/icons";
import { currentCongress, ordinal } from "@/lib/congress";

// Cached for 60s and re-fetched on the next request after that (ISR) —
// hearings only update every 2 hours anyway, so this is well within
// freshness tolerance, and it means repeat visits within that window are
// instant instead of re-running the whole query chain below.
export const revalidate = 60;

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
  const supabase = createPublicClient();
  const now = new Date();
  const today = isoDate(now);
  const weekEnd = addDays(today, 6);
  const activityStart = addDays(today, -7);
  const activityEnd = addDays(today, 7);

  const [
    { data: todayData, error: todayError },
    { data: todayLabelRow },
    { data: weekHearings },
    { data: weekLabels },
    { data: leadershipRows },
    { data: activityHearings },
    { data: activityVotes },
  ] = await Promise.all([
    supabase
      .from("hearings")
      .select("id, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
      .eq("date", today)
      .order("time", { ascending: true }),
    supabase.from("domewatch_calendar").select("labels").eq("date", today).maybeSingle(),
    supabase
      .from("hearings")
      .select("id, date, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
      .gte("date", today)
      .lte("date", weekEnd)
      .order("time", { ascending: true }),
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
    supabase
      .from("votes")
      .select("congress, session, chamber, roll_number, date, question, bill_number, result")
      .order("date", { ascending: false })
      .order("roll_number", { ascending: false })
      .limit(5),
  ]);

  const todayHearings = (todayData ?? []) as Hearing[];
  const todayLabels = (todayLabelRow?.labels ?? []) as string[];
  const nextUp = todayHearings.find((h) => !h.cancelled) ?? null;

  const weekHearingsByDate = new Map<string, Hearing[]>();
  for (const h of (weekHearings ?? []) as Hearing[]) {
    const key = h.date ?? "unknown";
    if (!weekHearingsByDate.has(key)) weekHearingsByDate.set(key, []);
    weekHearingsByDate.get(key)!.push(h);
  }
  const weekLabelsByDate = new Map<string, string[]>();
  for (const row of weekLabels ?? []) {
    weekLabelsByDate.set(row.date, (row.labels ?? []) as string[]);
  }
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const iso = addDays(today, i);
    const hearings = weekHearingsByDate.get(iso) ?? [];
    return {
      iso,
      dayLabel: dayAbbrev(iso),
      dayNum: Number(iso.slice(8, 10)),
      isToday: iso === today,
      count: hearings.filter((h) => !h.cancelled).length,
      hasLabel: (weekLabelsByDate.get(iso) ?? []).length > 0,
      hearings,
    };
  });
  const { congress } = currentCongress(today);

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

  type ActivityItem = {
    key: string;
    sortKey: string;
    href: string;
    cancelled: boolean;
    title: string;
    desc: string;
    icon: "vote" | "bolt" | "cancelled";
  };

  const hearingActivity: ActivityItem[] = ((activityHearings ?? []) as Hearing[])
    .filter((h) => h.changes.length > 0)
    .map((h) => {
      const lastChange = h.changes[h.changes.length - 1];
      const isCancelled = lastChange.toLowerCase().includes("cancel");
      return {
        key: `hearing-${h.id}`,
        sortKey: h.updated_at ?? "",
        href: `/calendar?month=${(h.date ?? today).slice(0, 7)}`,
        cancelled: isCancelled,
        title: h.committee,
        desc: lastChange,
        icon: isCancelled ? "cancelled" : "bolt",
      };
    });

  // There's no bill-tracking data source wired up (yet) to link to the
  // underlying legislation itself — this links to the vote's own detail
  // page, which is the most concrete "go see the thing" available today.
  const voteActivity: ActivityItem[] = ((activityVotes ?? []) as Vote[]).map((v) => ({
    key: `vote-${voteSlug(v)}`,
    sortKey: `${v.date}T12:00:00`,
    href: `/votes/${voteSlug(v)}`,
    cancelled: false,
    title: `${v.chamber} Roll Call ${v.roll_number}${v.bill_number ? ` · ${v.bill_number}` : ""}`,
    desc: `${v.question} — ${v.result}`,
    icon: "vote",
  }));

  const recentActivity = [...hearingActivity, ...voteActivity]
    .sort((a, b) => b.sortKey.localeCompare(a.sortKey))
    .slice(0, 6);

  return (
    <div className="page">
      <Header title="Dashboard" timestamp="Your overview of what's happening in Congress right now." />
      <div className="congress-badge">{ordinal(congress)} Congress</div>

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
          <DashboardWeekStrip days={weekDays} />
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
              <div className="panel dash-activity-panel">
                {recentActivity.map((item) => (
                  <Link href={item.href} className="dash-activity-item" key={item.key}>
                    <span className={`dash-activity-item__icon${item.icon === "cancelled" ? " dash-activity-item__icon--cancelled" : ""}`}>
                      {item.icon === "cancelled" ? <XIcon size={10} /> : item.icon === "vote" ? <VoteIcon size={13} /> : <BoltIcon />}
                    </span>
                    <span className="dash-activity-item__body">
                      <span className="dash-activity-item__title">{item.title}</span>
                      <span className="dash-activity-item__desc">{item.desc}</span>
                    </span>
                    <ChevronIcon className="dash-activity-item__chevron" />
                  </Link>
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
