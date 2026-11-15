"use client";

import { useState } from "react";
import type { MemberTerm } from "@/lib/types";
import { ChevronIcon } from "./icons";

function formatDate(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Intl.DateTimeFormat("en-US", { year: "numeric", month: "short", day: "numeric" }).format(
    new Date(Date.UTC(y, m - 1, d, 12)),
  );
}

function TermRow({ t }: { t: MemberTerm }) {
  return (
    <div className="term-item">
      <div className={`term-item__chamber bc-${t.chamber === "Senate" ? "senate" : "house"}`}>
        {t.chamber === "Senate" ? "Senate" : "House"}
      </div>
      <div className="term-item__body">
        <div className="term-item__seat">
          {t.state}
          {t.chamber === "House" ? `-${t.district ?? "AL"}` : ""}
          {t.party ? ` · ${t.party}` : ""}
        </div>
        <div className="term-item__dates">
          {formatDate(t.start_date)} – {t.end_date ? formatDate(t.end_date) : "Present"}
        </div>
      </div>
      {!t.end_date && <span className="tag tag-senate">Current</span>}
    </div>
  );
}

export default function TermHistory({ terms }: { terms: MemberTerm[] }) {
  const [open, setOpen] = useState(false);

  if (terms.length === 0) {
    return <div className="empty">No term records on file.</div>;
  }

  // terms arrives sorted most-recent-first. Always show the open (current)
  // term(s) inline; if there isn't one (a former member), show just the
  // single most recent term inline instead. Everything else collapses
  // behind a toggle — a one-term member never sees a dropdown at all.
  const hasOpenTerm = terms.some((t) => !t.end_date);
  const inline = hasOpenTerm ? terms.filter((t) => !t.end_date) : terms.slice(0, 1);
  const past = hasOpenTerm ? terms.filter((t) => t.end_date) : terms.slice(1);

  return (
    <div className="term-list">
      {inline.map((t, i) => (
        <TermRow t={t} key={`inline-${i}`} />
      ))}
      {past.length > 0 && (
        <>
          <button className="term-history-toggle" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
            <ChevronIcon className={`term-history-toggle__chevron${open ? " term-history-toggle__chevron--open" : ""}`} />
            {open ? "Hide" : "Show"} {past.length} past term{past.length !== 1 ? "s" : ""}
          </button>
          <div className={`term-history-collapse${open ? " term-history-collapse--open" : ""}`}>
            <div className="term-history-collapse__inner">
              {past.map((t, i) => (
                <TermRow t={t} key={`past-${i}`} />
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
