import { createClient } from "@/lib/supabase/server";
import type { InstitutionalLeadership, Member } from "@/lib/types";
import Header from "@/components/Header";
import MemberDirectory from "@/components/MemberDirectory";

export const dynamic = "force-dynamic";

export default async function MembersPage() {
  const supabase = await createClient();

  const [{ data: members, error: membersError }, { data: leadership }] = await Promise.all([
    supabase
      .from("members")
      .select("bioguide_id, full_name, nickname, delegate, bio, is_current, member_terms(member_id, chamber, state, district, party, start_date, end_date)")
      .eq("is_current", true)
      .order("full_name", { ascending: true }),
    supabase.from("institutional_leadership").select("bioguide_id, label, full_title, tier"),
  ]);

  return (
    <div className="page">
      <Header title="Members of Congress" timestamp={`${(members ?? []).length} current members · House and Senate`} />
      {membersError ? (
        <div className="panel" style={{ marginTop: 18 }}>
          <div className="row" style={{ color: "var(--text-dim)" }}>
            Couldn&apos;t reach Supabase: {membersError.message}
          </div>
        </div>
      ) : (
        <MemberDirectory
          members={(members ?? []) as Member[]}
          leadership={(leadership ?? []) as InstitutionalLeadership[]}
        />
      )}
    </div>
  );
}
