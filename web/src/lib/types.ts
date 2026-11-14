export type Chamber = "Senate" | "House" | "Joint";

export type Hearing = {
  id: number;
  date?: string;
  chamber: Chamber;
  committee: string;
  chair: string | null;
  time: string | null;
  building: string | null;
  room: string | null;
  topic: string | null;
  details: string | null;
  witnesses: string[];
  cancelled: boolean;
  changes: string[];
  link: string | null;
};

export type MemberChamber = "House" | "Senate";

export type MemberTerm = {
  member_id: string;
  chamber: MemberChamber;
  state: string;
  district: string | null;
  party: string | null;
  start_date: string;
  end_date: string | null;
};

export type Member = {
  bioguide_id: string;
  full_name: string;
  nickname: string | null;
  delegate: boolean;
  bio: string | null;
  is_current: boolean;
  member_terms: MemberTerm[];
};

export type InstitutionalLeadership = {
  bioguide_id: string;
  label: string;
  full_title: string;
  tier: number;
};
