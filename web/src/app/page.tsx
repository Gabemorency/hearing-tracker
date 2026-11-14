import { createClient } from "@/lib/supabase/server";

// Always rendered per-request — this page reads live data, and without
// this Next would try to prerender it at build time (failing wherever
// Supabase env vars aren't set, e.g. a fresh checkout or CI).
export const dynamic = "force-dynamic";

// Phase 0 proof-of-life: confirms the Next.js app can actually reach
// Supabase and read through RLS. Expect 0 rows until Phase 2 points the
// scraper's write path here — an empty, error-free result is success for
// this page's purpose, not a bug.
export default async function Home() {
  const supabase = await createClient();
  const today = new Date().toISOString().slice(0, 10);

  const { data: hearings, error } = await supabase
    .from("hearings")
    .select("id, chamber, committee, topic, time")
    .eq("date", today)
    .order("time", { ascending: true });

  return (
    <main>
      <div className="header-eyebrow sub" style={{ fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--gold)" }}>
        Congressional Hearing Tracker
      </div>
      <h1>Today&apos;s Hearings</h1>
      <p className="sub">{today} · reading from Supabase</p>

      <div className="panel" style={{ marginTop: 18 }}>
        {error ? (
          <div className="row" style={{ color: "var(--text-dim)" }}>
            Couldn&apos;t reach Supabase: {error.message}
          </div>
        ) : hearings && hearings.length > 0 ? (
          hearings.map((h) => (
            <div className="row" key={h.id}>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--text-secondary)" }}>
                {h.time} · {h.chamber}
              </div>
              <div style={{ fontWeight: 600, marginTop: 2 }}>{h.committee}</div>
              <div className="sub" style={{ fontSize: 12, marginTop: 2 }}>{h.topic}</div>
            </div>
          ))
        ) : (
          <div className="empty">
            No hearings in Supabase yet — expected until the scraper&apos;s
            write path is pointed here (Phase 2).
          </div>
        )}
      </div>
    </main>
  );
}
