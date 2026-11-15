import { createClient } from "@/lib/supabase/server";
import type { CommitteeMembership } from "@/lib/types";
import Header from "@/components/Header";
import ErrorPanel from "@/components/ErrorPanel";
import SourceNote from "@/components/SourceNote";
import CommitteeDirectory, { type CommitteeGroup } from "@/components/CommitteeDirectory";

export const dynamic = "force-dynamic";

function roleRank(role: string) {
  const r = role.toLowerCase();
  if (r.includes("chair") && !r.includes("ranking")) return 0;
  if (r.includes("ranking")) return 1;
  if (r.includes("vice chair")) return 2;
  return 3;
}

export default async function CommitteesPage() {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("committee_memberships")
    .select("committee, chamber, role, rank, is_full_committee, member_id, members(full_name, bioguide_id)")
    .eq("is_full_committee", true)
    .order("committee", { ascending: true });

  const rows = (data ?? []) as unknown as CommitteeMembership[];

  const groups = new Map<string, CommitteeGroup>();
  for (const row of rows) {
    if (!row.members) continue;
    if (!groups.has(row.committee)) {
      groups.set(row.committee, { committee: row.committee, chamber: row.chamber, members: [] });
    }
    groups.get(row.committee)!.members.push({
      bioguide_id: row.members.bioguide_id,
      full_name: row.members.full_name,
      role: row.role,
      rank: row.rank,
    });
  }

  const committees = [...groups.values()]
    .map((g) => ({
      ...g,
      members: [...g.members].sort((a, b) => {
        const ra = roleRank(a.role);
        const rb = roleRank(b.role);
        if (ra !== rb) return ra - rb;
        return (a.rank ?? 999) - (b.rank ?? 999);
      }),
    }))
    .sort((a, b) => a.committee.localeCompare(b.committee));

  return (
    <div className="page">
      <Header title="Committees" timestamp={`${committees.length} standing committees · House, Senate, and Joint`} />
      {error ? (
        <ErrorPanel message={error.message} />
      ) : (
        <>
          <CommitteeDirectory committees={committees} />
          <SourceNote>Committee rosters: unitedstates/congress-legislators</SourceNote>
        </>
      )}
    </div>
  );
}
