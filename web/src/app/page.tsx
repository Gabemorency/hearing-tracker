import { createClient } from "@/lib/supabase/server";
import type { Hearing } from "@/lib/types";
import Header from "@/components/Header";
import StatsBar from "@/components/StatsBar";
import HearingList from "@/components/HearingList";

// Always rendered per-request — this page reads live data, and without
// this Next would try to prerender it at build time (failing wherever
// Supabase env vars aren't set, e.g. a fresh checkout or CI).
export const dynamic = "force-dynamic";

function formatTimestamp(now: Date) {
  const datePart = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(now);
  const timePart = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  }).format(now);
  return `As of ${timePart} ET · ${datePart} · Updates every 2 hours · Schedules subject to change.`;
}

export default async function Home() {
  const supabase = await createClient();
  const now = new Date();
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(now); // en-CA -> YYYY-MM-DD

  const { data, error } = await supabase
    .from("hearings")
    .select("id, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link")
    .eq("date", today)
    .order("time", { ascending: true });

  const hearings = (data ?? []) as Hearing[];

  const active = hearings.filter((h) => !h.cancelled).length;
  const senate = hearings.filter((h) => h.chamber === "Senate").length;
  const house = hearings.filter((h) => h.chamber === "House").length;
  const joint = hearings.filter((h) => h.chamber === "Joint").length;

  return (
    <div className="page">
      <Header title="Today's Hearings" timestamp={formatTimestamp(now)} />
      {error ? (
        <div className="panel" style={{ marginTop: 18 }}>
          <div className="row" style={{ color: "var(--text-dim)" }}>
            Couldn&apos;t reach Supabase: {error.message}
          </div>
        </div>
      ) : (
        <>
          <StatsBar active={active} total={hearings.length} senate={senate} house={house} joint={joint} />
          <HearingList hearings={hearings} />
        </>
      )}
    </div>
  );
}
