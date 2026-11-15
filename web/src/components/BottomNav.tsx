"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { GavelIcon, PeopleIcon, CalendarGridIcon, SearchIcon } from "./icons";

const NAV = [
  { href: "/", label: "Hearings", Icon: GavelIcon },
  { href: "/members", label: "Members", Icon: PeopleIcon },
  { href: "/calendar", label: "Calendar", Icon: CalendarGridIcon },
  { href: "/search", label: "Search", Icon: SearchIcon },
] as const;

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="bottom-nav" aria-label="Primary">
      {NAV.map(({ href, label, Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`bottom-nav__item${active ? " bottom-nav__item--active" : ""}`}
          >
            <Icon size={21} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
