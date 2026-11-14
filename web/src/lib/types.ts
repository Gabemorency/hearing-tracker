export type Chamber = "Senate" | "House" | "Joint";

export type Hearing = {
  id: number;
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
