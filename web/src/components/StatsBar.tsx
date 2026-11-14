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
  const stats: Array<[string, number, string, string]> = [
    ["Active", active, "var(--stat-active)", "var(--stat-active)"],
    ["Total", total, "var(--text-secondary)", "var(--text-muted)"],
    ["Senate", senate, "var(--gold)", "var(--gold)"],
    ["House", house, "var(--blue)", "var(--blue)"],
    ["Joint", joint, "var(--purple)", "var(--purple)"],
  ];
  return (
    <div className="stats">
      {stats.map(([label, value, color, accent]) => (
        <div className="stat" key={label} style={{ borderTopColor: accent }}>
          <div className="stat-number" style={{ color }}>
            {value}
          </div>
          <div className="stat-label">{label}</div>
        </div>
      ))}
    </div>
  );
}
