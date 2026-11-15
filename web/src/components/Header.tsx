import ThemeToggle from "./ThemeToggle";
import { CapitolIcon } from "./icons";

export default function Header({
  title,
  timestamp,
}: {
  title: string;
  timestamp: string;
}) {
  return (
    <div className="header">
      <div className="header-left">
        <div className="header-eyebrow">
          <CapitolIcon className="header-eyebrow__icon" />
          Congressional Hearing Tracker
        </div>
        <h1>{title}</h1>
        <div className="header-timestamp">{timestamp}</div>
      </div>
      <ThemeToggle />
    </div>
  );
}
