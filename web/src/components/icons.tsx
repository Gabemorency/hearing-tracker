// Small inline SVG marks, all currentColor so they inherit tag/theme
// colors automatically. Replaces emoji (🏛 🌙 ☀️ ⚡ ✕ 🔴 ℹ) which render
// inconsistently across platforms and read as a placeholder, not a
// finished institutional UI.

type IconProps = { size?: number; className?: string };

export function CapitolIcon({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 2.5 20 7.5V9H4V7.5L12 2.5Z"
        fill="currentColor"
      />
      <rect x="11" y="9" width="2" height="10" fill="currentColor" />
      <rect x="6" y="9" width="2" height="10" fill="currentColor" />
      <rect x="16" y="9" width="2" height="10" fill="currentColor" />
      <rect x="3" y="19.5" width="18" height="2" fill="currentColor" />
    </svg>
  );
}

export function SunIcon({ size = 15, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="4.2" />
      <path d="M12 2.5v2.4M12 19.1v2.4M4.9 4.9l1.7 1.7M17.4 17.4l1.7 1.7M2.5 12h2.4M19.1 12h2.4M4.9 19.1l1.7-1.7M17.4 6.6l1.7-1.7" />
    </svg>
  );
}

export function MoonIcon({ size = 15, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M20.2 14.6A8.6 8.6 0 1 1 9.4 3.8a7 7 0 0 0 10.8 10.8Z" />
    </svg>
  );
}

export function BoltIcon({ size = 10, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" className={className} aria-hidden="true">
      <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
    </svg>
  );
}

export function XIcon({ size = 10, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" className={className} aria-hidden="true">
      <path d="M5 5l14 14M19 5 5 19" />
    </svg>
  );
}

export function InfoIcon({ size = 11, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9.2" />
      <path d="M12 11v5.5" />
      <circle cx="12" cy="7.6" r="0.2" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function SearchIcon({ size = 14, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className={className} aria-hidden="true">
      <circle cx="10.8" cy="10.8" r="6.8" />
      <path d="M20 20l-4.4-4.4" />
    </svg>
  );
}

export function ChevronIcon({ size = 12, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

export function ExternalLinkIcon({ size = 11, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M7 17 17 7M9 7h8v8" />
    </svg>
  );
}

export function LiveDotIcon({ size = 9, className }: IconProps) {
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" className={className} aria-hidden="true">
      <circle cx="5" cy="5" r="5" fill="currentColor" className="live-dot__ring" opacity="0.35" />
      <circle cx="5" cy="5" r="2.6" fill="currentColor" />
    </svg>
  );
}
