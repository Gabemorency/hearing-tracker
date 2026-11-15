export type Chamber = "Senate" | "House" | "Joint";

export type Hearing = {
  id: number;
  date?: string;
  updated_at?: string;
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
  photo_url: string | null;
  member_terms: MemberTerm[];
};

export type InstitutionalLeadership = {
  bioguide_id: string;
  label: string;
  full_title: string;
  tier: number;
};

export type VotePosition = "Yea" | "Nay" | "Present" | "Not Voting";

export type Vote = {
  congress: number;
  session: number;
  chamber: MemberChamber;
  roll_number: number;
  date: string;
  question: string;
  description: string | null;
  bill_number: string | null;
  result: string;
  yea_count: number;
  nay_count: number;
  present_count: number;
  not_voting_count: number;
};

export type MemberVote = {
  congress: number;
  session: number;
  chamber: MemberChamber;
  roll_number: number;
  member_id: string;
  position: VotePosition;
  members?: { full_name: string; bioguide_id: string } | null;
};

export type CommitteeMembership = {
  committee: string;
  chamber: MemberChamber | "Joint";
  role: string;
  rank: number | null;
  is_full_committee: boolean;
  member_id: string;
  members: { full_name: string; bioguide_id: string } | null;
};
