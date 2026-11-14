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
    ["House", house, "var(--blue)"],
    ["Joint", joint, "var(--purple)"],
  ];
  return (
    <div className="stats">
      {stats.map(([label, value, color]) => (
        <div className="stat" key={label}>
          <div className="stat-number" style={{ color }}>
            {value}
          </div>
          <div className="stat-label">{label}</div>
        </div>
      ))}
    </div>
  );
}
