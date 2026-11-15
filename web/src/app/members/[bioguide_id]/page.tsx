import { notFound } from "next/navigation";
import Link from "next/link";
import { ViewTransition } from "react";
import { createPublicClient } from "@/lib/supabase/public";
import type { InstitutionalLeadership, Member } from "@/lib/types";
import Header from "@/components/Header";
import { currentTerm, initials, partyClass } from "@/components/MemberCard";
import ErrorPanel from "@/components/ErrorPanel";
import MemberAvatar from "@/components/MemberAvatar";
import SourceNote from "@/components/SourceNote";
import DistrictMap, { type DistrictGeometry } from "@/components/DistrictMap";
import TermHistory from "@/components/TermHistory";
import { currentCongress } from "@/lib/congress";

// Cached for 5 minutes per bioguide_id (ISR) — a member's bio/terms only
// change on the nightly sync. Pages are generated on-demand per id on
// first visit, not all up front at build time.
export const revalidate = 300;

export default async function MemberDetailPage({
  params,
}: {
  params: Promise<{ bioguide_id: string }>;
}) {
  const { bioguide_id } = await params;
  const supabase = createPublicClient();

  const [{ data: member, error }, { data: leadership }] = await Promise.all([
    supabase
      .from("members")
      .select(
        "bioguide_id, full_name, nickname, delegate, bio, is_current, photo_url, member_terms(member_id, chamber, state, district, party, start_date, end_date)",
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

  let stateGeometry: DistrictGeometry | null = null;
  const districtEntries: { id: string; geometry: DistrictGeometry }[] = [];
  let highlightId: string | undefined;
  let mapLabel = "";
  if (term) {
    highlightId = term.chamber === "Senate" ? undefined : (term.district ?? "0");
    mapLabel = term.chamber === "Senate" ? term.state : `${term.state}-${term.district ?? "AL"}`;
    const todayIso = new Date().toISOString().slice(0, 10);
    const { congress } = currentCongress(todayIso);
    const { data: shapeRows } = await supabase
      .from("district_shapes")
      .select("district, geometry")
      .eq("congress", congress)
      .eq("state", term.state);
    for (const row of shapeRows ?? []) {
      if (row.district === "") {
        stateGeometry = row.geometry as DistrictGeometry;
      } else {
        districtEntries.push({ id: row.district, geometry: row.geometry as DistrictGeometry });
      }
    }
  }

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
        <ViewTransition name={`member-avatar-${m.bioguide_id}`}>
          <MemberAvatar photoUrl={m.photo_url} initials={initials(m.full_name)} partyClass={pc} name={m.full_name} large />
        </ViewTransition>
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

      {stateGeometry && (
        <div className="panel district-map-panel">
          <DistrictMap
            stateGeometry={stateGeometry}
            districts={districtEntries}
            highlightId={highlightId}
            size={220}
            label={`Map of ${mapLabel}`}
          />
          <div className="district-map-caption">{mapLabel}</div>
        </div>
      )}

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
      <TermHistory terms={terms} />

      <SourceNote>Member data: unitedstates/congress-legislators · Photos: unitedstates/images</SourceNote>
    </div>
  );
}
