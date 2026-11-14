"use client";

import { useState } from "react";
import type { Hearing } from "@/lib/types";

function chamberClass(chamber: string) {
  return chamber === "Senate" ? "senate" : chamber === "House" ? "house" : "joint";
}

export default function HearingCard({ hearing: h }: { hearing: Hearing }) {
  const [open, setOpen] = useState(false);
  const c = chamberClass(h.chamber);
  const hasChanges = h.changes.length > 0;

  const realWitnesses =
    h.witnesses.length > 0 && !h.witnesses.every((w) => w === "Witnesses not yet publicly posted")
      ? h.witnesses
      : null;

  const hasAbout =
    h.details && h.details.trim() && h.details.trim() !== (h.topic ?? "").trim() && h.details.length > (h.topic?.length ?? 0) + 20;

  return (
    <div
      className={["card", `chamber-${c}`, h.cancelled ? "cancelled" : "", hasChanges ? "has-changes" : "", open ? "open" : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={() => setOpen((o) => !o)}
    >
      <div className="card-top">
        <div className="card-left">
          <div className="card-meta">
            <span className={`tag tag-${c}`}>{h.chamber}</span>
            {h.cancelled && <span className="tag tag-cancelled">Cancelled</span>}
            <span className="card-time">{h.time}</span>
          </div>
          <div className="card-committee">{h.committee}</div>
          <div className="card-topic">{h.topic}</div>
          {hasChanges && (
            <div className="change-pills">
              {h.changes.map((ch) => (
                <span
                  key={ch}
                  className={`change-pill${ch.toLowerCase().includes("cancel") ? " cancelled-pill" : ""}`}
                >
                  ⚡ {ch}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="card-right">
          <div className={`card-building bc-${c}`}>{h.building}</div>
          <div className="card-room">{h.room}</div>
        </div>
      </div>

      <div className="card-body">
        <div className="card-section">
          <div className={`card-section-label sl-${c}`}>Chair</div>
          <div className="card-section-value">
            {h.chair || <span className="faint-italic">Not yet posted</span>}
          </div>
        </div>
        {hasAbout && (
          <div className="card-section">
            <div className={`card-section-label sl-${c}`}>About</div>
            <div className="card-section-value">{h.details}</div>
          </div>
        )}
        <div className="card-section">
          <div className={`card-section-label sl-${c}`}>Witnesses</div>
          {realWitnesses ? (
            realWitnesses.map((w) => (
              <div className={`witness wb-${c}`} key={w}>
                {w}
              </div>
            ))
          ) : (
            <div className="faint-italic" style={{ fontSize: 12, paddingLeft: 10 }}>
              Not yet posted
            </div>
          )}
        </div>
        {h.link && (
          <div className="card-section">
            <a className="watch-link" href={h.link} target="_blank" rel="noopener" onClick={(e) => e.stopPropagation()}>
              🔴 Watch / committee hearings page ↗
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
