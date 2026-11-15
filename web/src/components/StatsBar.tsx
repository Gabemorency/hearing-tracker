"use client";

import { useEffect, useState } from "react";

// Counts up from 0 to the real value on mount — numbers that move feel
// alive, and it's a genuinely interactive cue that "this data just
// loaded," not just decoration.
function useCountUp(target: number, durationMs = 550) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(Math.round(target * eased));
      if (progress < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, durationMs]);
  return value;
}

function StatCell({ label, value, color }: { label: string; value: number; color: string }) {
  const displayValue = useCountUp(value);
  return (
    <div className="stat">
      <div className="stat-number" style={{ color }}>
        {displayValue}
      </div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export default function StatsBar({
  active,
  total,
  senate,
  house,
  joint,
}: {
  active: number;
  total: number;
  senate: number;
  house: number;
  joint: number;
}) {
  const stats: Array<[string, number, string]> = [
    ["Active", active, "var(--stat-active)"],
    ["Total", total, "var(--text-secondary)"],
    ["Senate", senate, "var(--gold)"],
    ["House", house, "var(--teal)"],
    ["Joint", joint, "var(--purple)"],
  ];
  return (
    <div className="stats">
      {stats.map(([label, value, color]) => (
        <StatCell key={label} label={label} value={value} color={color} />
      ))}
    </div>
  );
}
