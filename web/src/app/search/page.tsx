import { createPublicClient } from "@/lib/supabase/public";
import type { Hearing } from "@/lib/types";
import Header from "@/components/Header";
import HearingCard from "@/components/HearingCard";
import { CapitolIcon, SearchIcon } from "@/components/icons";
import ErrorPanel from "@/components/ErrorPanel";
import SourceNote from "@/components/SourceNote";

// Reading `searchParams` (for ?q=) forces fully dynamic rendering the same
// way cookies()/headers() do, so `revalidate` wouldn't do anything here —
// no ISR caching for this one without opting into Cache Components.

function formatDateLabel(iso: string) {
  if (iso === "unknown") return "Unknown date";
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(Date.UTC(y, m - 1, d, 12));
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = (q ?? "").trim();
  const supabase = createPublicClient();

  let hearings: Hearing[] = [];
  let error: string | null = null;

  if (query) {
    const { data, error: err } = await supabase
      .from("hearings")
      .select(
        "id, date, chamber, committee, chair, time, building, room, topic, details, witnesses, cancelled, changes, link",
      )
      .textSearch("search_vector", query, { type: "websearch", config: "english" })
      .order("date", { ascending: false })
      .order("time", { ascending: true })
      .limit(200);
    if (err) error = err.message;
    hearings = (data ?? []) as Hearing[];
  }

  const byDate = new Map<string, Hearing[]>();
  for (const h of hearings) {
    const key = h.date ?? "unknown";
    if (!byDate.has(key)) byDate.set(key, []);
    byDate.get(key)!.push(h);
  }
  const dates = [...byDate.keys()].sort().reverse();

  return (
    <div className="page">
      <Header
        title="Search Hearings"
        timestamp="Full-text search across every hearing on record — topic, committee, and witness names."
      />

      <form action="/search" method="GET" className="search-row">
        <SearchIcon />
        <input
          className="search-input"
          type="text"
          name="q"
          defaultValue={query}
          placeholder="Search topics, committees, witnesses…"
        />
      </form>

      {error ? (
        <ErrorPanel message={error} />
      ) : !query ? (
        <div className="cards">
          <div className="empty empty--hero">
            <SearchIcon size={32} className="empty__icon" />
            <div className="empty__title">Search every hearing on record</div>
            <div className="empty__sub">
              Try a topic, a committee name, or a witness — e.g. &quot;artificial intelligence&quot; or
              &quot;Judiciary&quot;.
            </div>
          </div>
        </div>
      ) : dates.length === 0 ? (
        <div className="cards">
          <div className="empty empty--hero">
            <CapitolIcon size={32} className="empty__icon" />
            <div className="empty__title">No matches for &quot;{query}&quot;</div>
            <div className="empty__sub">Try different or broader terms.</div>
          </div>
        </div>
      ) : (
        <>
          <div className="count-label">
            {hearings.length} result{hearings.length !== 1 ? "s" : ""} across {dates.length} day
            {dates.length !== 1 ? "s" : ""}
          </div>
          {dates.map((date) => (
            <div className="calendar-day" key={date}>
              <div className="calendar-day-header">
                <div className="calendar-day-title">{formatDateLabel(date)}</div>
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
          ))}
        </>
      )}
      {!error && (
        <SourceNote>Auto-updated every 2 hrs · docs.house.gov · senate.gov · Individual committee pages</SourceNote>
      )}
    </div>
  );
}
