// Self-computing, same convention as the Python scrapers' ET/DST offset —
// no hardcoded congress number to remember to bump every two years. A new
// Congress is sworn in at noon ET on January 3rd of each odd year.
export function currentCongress(iso: string) {
  const [y, m, d] = iso.split("-").map(Number);
  const effectiveYear = m === 1 && d < 3 ? y - 1 : y;
  const congress = Math.floor((effectiveYear - 1789) / 2) + 1;
  const session = (effectiveYear - 1789) % 2 === 0 ? 1 : 2;
  return { congress, session };
}

export function ordinal(n: number) {
  const v = n % 100;
  if (v >= 11 && v <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}
