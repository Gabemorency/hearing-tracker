import type { Vote } from "./types";

// Shared by both server components (dashboard, /votes, member detail —
// building links/keys) and the client VoteCard component. Kept out of
// VoteCard.tsx itself because that file is "use client", and a server
// component can't call a function from a client module.
export function voteSlug(v: Pick<Vote, "chamber" | "congress" | "session" | "roll_number">) {
  return `${v.chamber.toLowerCase()}-${v.congress}-${v.session}-${v.roll_number}`;
}
