"use client";

import { useState } from "react";
import type { Hearing } from "@/lib/types";
import { BoltIcon, ChevronIcon, LiveDotIcon, XIcon } from "./icons";

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
            {h.cancelled && (
              <span className="tag tag-cancelled">
                <XIcon size={8} /> Cancelled
              </span>
            )}
            <span className="card-time">{h.time}</span>
          </div>
          <div className="card-committee">{h.committee}</div>
          <div className="card-topic">{h.topic}</div>
          {hasChanges && (
            <span className="tag tag-updated" style={{ marginTop: 6 }}>
              <BoltIcon /> {h.changes.length} update{h.changes.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <div className="card-right">
          <div className={`card-building bc-${c}`}>{h.building}</div>
          <div className="card-room">{h.room}</div>
          <ChevronIcon className="card-chevron" />
        </div>
      </div>

      <div className="card-body">
        <div className="card-body__inner">
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
                <LiveDotIcon className="watch-link__dot" /> Watch / committee hearings page
              </a>
            </div>
          )}
          {hasChanges && (
            <div className="card-section">
              <div className={`card-section-label sl-${c}`}>Update History</div>
              <div className="update-timeline">
                {[...h.changes].reverse().map((ch) => {
                  const idx = ch.lastIndexOf(" · ");
                  const desc = idx >= 0 ? ch.slice(0, idx) : ch;
                  const stamp = idx >= 0 ? ch.slice(idx + 3) : "";
                  const isCancelled = desc.toLowerCase().includes("cancel");
                  return (
                    <div className={`update-timeline-item${isCancelled ? " cancelled" : ""}`} key={ch}>
                      <span className="update-timeline-item__dot" />
                      <span>
                        {desc}
                        {stamp && <span className="update-timeline-item__stamp"> · {stamp}</span>}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
