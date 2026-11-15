import { notFound } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import type { InstitutionalLeadership, Member } from "@/lib/types";
import Header from "@/components/Header";
import { currentTerm, initials, partyClass } from "@/components/MemberCard";
import ErrorPanel from "@/components/ErrorPanel";

export const dynamic = "force-dynamic";

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d, 12)),
  );
}

export default async function MemberDetailPage({
  params,
}: {
  params: Promise<{ bioguide_id: string }>;
}) {
  const { bioguide_id } = await params;
  const supabase = await createClient();

  const [{ data: member, error }, { data: leadership }] = await Promise.all([
    supabase
      .from("members")
      .select(
        "bioguide_id, full_name, nickname, delegate, bio, is_current, member_terms(member_id, chamber, state, district, party, start_date, end_date)",
      )
      .eq("bioguide_id", bioguide_id)
      .maybeSingle(),
    supabase
      .from("institutional_leadership")
      .select("bioguide_id, label, full_title, tier")
      .eq("bioguide_id", bioguide_id)
      .maybeSingle(),
  ]);

  if (error) {
    return (
      <div className="page">
        <Header title="Member" timestamp="" />
        <ErrorPanel message={error.message} />
      </div>
    );
  }

  if (!member) {
    notFound();
  }

  const m = member as Member;
  const term = currentTerm(m.member_terms);
  const pc = partyClass(term?.party ?? null);
  const terms = [...m.member_terms].sort((a, b) => b.start_date.localeCompare(a.start_date));

  const seatLine = term
    ? term.chamber === "Senate"
      ? `U.S. Senator for ${term.state}${term.party ? ` · ${term.party}` : ""}`
      : `U.S. Representative for ${term.state}'s ${term.district ?? "At-Large"} District${term.party ? ` · ${term.party}` : ""}`
    : m.is_current
      ? "Current member — seat on file not found"
      : "Former member of Congress";

  return (
    <div className="page">
      <Header title={m.full_name} timestamp={seatLine} />

      <Link href="/members" className="back-link">
        ← All members
      </Link>

      <div className="member-detail">
        <div className={`member-avatar member-avatar--lg ${pc}`}>{initials(m.full_name)}</div>
        <div className="member-detail__info">
          <div className="member-detail__name">
            {m.full_name}
            {!m.is_current && <span className="tag tag-cancelled" style={{ marginLeft: 8 }}>Former Member</span>}
          </div>
          {leadership && (
            <div className="member-leadership" style={{ marginTop: 6 }}>
              {(leadership as InstitutionalLeadership).full_title}
            </div>
          )}
          {m.delegate && <div className="member-detail__note">Non-voting delegate</div>}
        </div>
      </div>

      {m.bio && (
        <div className="panel" style={{ marginTop: 18, padding: "16px 18px" }}>
          <div className="card-section-label sl-senate" style={{ marginBottom: 8 }}>
            Biography
          </div>
          {m.bio.split("\n\n").map((para, i) => (
            <p key={i} className="member-bio-paragraph">
              {para}
            </p>
          ))}
        </div>
      )}

      <h2>Term History</h2>
      {terms.length === 0 ? (
        <div className="empty">No term records on file.</div>
      ) : (
        <div className="term-list">
          {terms.map((t, i) => (
            <div className="term-item" key={i}>
              <div className={`term-item__chamber bc-${t.chamber === "Senate" ? "senate" : "house"}`}>
                {t.chamber === "Senate" ? "Senate" : "House"}
              </div>
              <div className="term-item__body">
                <div className="term-item__seat">
                  {t.state}
                  {t.chamber === "House" ? `-${t.district ?? "AL"}` : ""}
                  {t.party ? ` · ${t.party}` : ""}
                </div>
                <div className="term-item__dates">
                  {formatDate(t.start_date)} – {t.end_date ? formatDate(t.end_date) : "Present"}
                </div>
              </div>
              {!t.end_date && <span className="tag tag-senate">Current</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
