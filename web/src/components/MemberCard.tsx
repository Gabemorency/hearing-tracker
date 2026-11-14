import type { InstitutionalLeadership, Member, MemberTerm } from "@/lib/types";

export function currentTerm(terms: MemberTerm[]): MemberTerm | null {
  if (terms.length === 0) return null;
  const open = terms.find((t) => !t.end_date);
  if (open) return open;
  return [...terms].sort((a, b) => b.start_date.localeCompare(a.start_date))[0];
}

function partyClass(party: string | null) {
  if (!party) return "";
  const p = party[0]?.toUpperCase();
  if (p === "D") return "party-d";
  if (p === "R") return "party-r";
  return "party-i";
}

function initials(fullName: string) {
  const parts = fullName.split(" ").filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? "?";
  return `${parts[0][0] ?? ""}${parts[parts.length - 1][0] ?? ""}`.toUpperCase();
}

export default function MemberCard({ member, leadership }: { member: Member; leadership?: InstitutionalLeadership }) {
  const term = currentTerm(member.member_terms);
  const pc = partyClass(term?.party ?? null);

  const seat = term
    ? term.chamber === "Senate"
      ? `Sen. · ${term.state}${term.party ? ` (${term.party[0]})` : ""}`
      : `Rep. · ${term.state}-${term.district ?? "AL"}${term.party ? ` (${term.party[0]})` : ""}`
    : "Seat unknown";

  return (
    <div className="member-card">
      <div className={`member-avatar ${pc}`}>{initials(member.full_name)}</div>
      <div className="member-info">
        <div className="member-name">{member.full_name}</div>
        <div className="member-seat">{seat}</div>
        {leadership && <div className="member-leadership">{leadership.label}</div>}
      </div>
    </div>
  );
}
