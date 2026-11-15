import type { ReactNode } from "react";
import { InfoIcon } from "./icons";

export default function SourceNote({ children }: { children: ReactNode }) {
  return (
    <div className="source-note">
      <InfoIcon /> {children}
    </div>
  );
}
