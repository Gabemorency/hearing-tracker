"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { HomeIcon, GavelIcon, PeopleIcon, CalendarGridIcon, CommitteeIcon, SearchIcon } from "./icons";

const NAV = [
  { href: "/", label: "Home", Icon: HomeIcon },
  { href: "/hearings", label: "Hearings", Icon: GavelIcon },
  { href: "/members", label: "Members", Icon: PeopleIcon },
  { href: "/committees", label: "Committees", Icon: CommitteeIcon },
  { href: "/calendar", label: "Calendar", Icon: CalendarGridIcon },
  { href: "/search", label: "Search", Icon: SearchIcon },
] as const;

export default function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="bottom-nav" aria-label="Primary" id="bottom-nav" tabIndex={-1}>
      {NAV.map(({ href, label, Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link
            key={href}
            href={href}
            className={`bottom-nav__item${active ? " bottom-nav__item--active" : ""}`}
          >
            <Icon size={24} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
