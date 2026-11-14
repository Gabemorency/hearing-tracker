import Link from "next/link";
import ThemeToggle from "./ThemeToggle";

export default function Header({
  title,
  timestamp,
}: {
  title: string;
  timestamp: string;
}) {
  return (
    <>
      <div className="header">
        <div className="header-left">
          <div className="header-eyebrow">🏛 Congressional Hearing Tracker</div>
          <h1>{title}</h1>
          <div className="header-timestamp">{timestamp}</div>
        </div>
        <ThemeToggle />
      </div>
      <nav className="site-nav">
        <Link href="/" className="site-nav__link site-nav__link--active">
          Hearings
        </Link>
        <span className="site-nav__link site-nav__link--soon">Members</span>
        <span className="site-nav__link site-nav__link--soon">Calendar</span>
      </nav>
    </>
  );
}
