"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import ThemeToggle from "./ThemeToggle";
import { CapitolIcon } from "./icons";

const NAV = [
  { href: "/", label: "Hearings" },
  { href: "/members", label: "Members" },
  { href: "/calendar", label: "Calendar" },
] as const;

export default function Header({
  title,
  timestamp,
}: {
  title: string;
  timestamp: string;
}) {
  const pathname = usePathname();

  return (
    <>
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
      <nav className="site-nav">
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`site-nav__link${pathname === item.href ? " site-nav__link--active" : ""}`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
