import { createPublicClient } from "@/lib/supabase/public";
import type { InstitutionalLeadership, Member } from "@/lib/types";
import Header from "@/components/Header";
import MemberDirectory from "@/components/MemberDirectory";
import ErrorPanel from "@/components/ErrorPanel";
import SourceNote from "@/components/SourceNote";

// Cached for 5 minutes (ISR) — the roster only changes on the nightly sync.
export const revalidate = 300;

export default async function MembersPage() {
  const supabase = createPublicClient();

  const [{ data: members, error: membersError }, { data: leadership }] = await Promise.all([
    supabase
      .from("members")
      .select("bioguide_id, full_name, nickname, delegate, bio, is_current, photo_url, member_terms(member_id, chamber, state, district, party, start_date, end_date)")
      .eq("is_current", true)
      .order("full_name", { ascending: true }),
    supabase.from("institutional_leadership").select("bioguide_id, label, full_title, tier"),
  ]);

  return (
    <div className="page">
      <Header title="Members of Congress" timestamp={`${(members ?? []).length} current members · House and Senate`} />
      {membersError ? (
        <ErrorPanel message={membersError.message} />
      ) : (
        <>
          <MemberDirectory
            members={(members ?? []) as Member[]}
            leadership={(leadership ?? []) as InstitutionalLeadership[]}
          />
          <SourceNote>Member data: unitedstates/congress-legislators · Photos: unitedstates/images</SourceNote>
        </>
      )}
    </div>
  );
}
