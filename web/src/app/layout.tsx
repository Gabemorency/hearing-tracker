import type { Metadata, Viewport } from "next";
import { Playfair_Display, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
import BottomNav from "@/components/BottomNav";
import "./globals.css";

const playfair = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
  weight: ["700", "800"],
});
const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["300", "400", "600", "700"],
});
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "Congressional Hearing Tracker",
  description: "Track congressional hearings and browse member profiles",
};

// viewport-fit=cover is what makes env(safe-area-inset-bottom) resolve to
// a real value instead of 0 on phones with a home-indicator/gesture bar —
// without it, the bottom nav's safe-area padding was a no-op, so the nav
// sat flush against the very edge of the screen, visually colliding with
// the browser's own bottom chrome.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

// Runs before paint so there's no flash of the wrong theme: reads the
// stored preference (or system preference) and sets the `.light` class
// on <html> before React hydrates. Mirrors the static site's theme.css
// convention exactly, so both sites behave identically while they coexist.
const THEME_BOOTSTRAP = `
(function() {
  try {
    var stored = localStorage.getItem('theme');
    var theme = stored || (window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    if (theme === 'light') document.documentElement.classList.add('light');
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body className={`${playfair.variable} ${plexSans.variable} ${plexMono.variable}`}>
        <a href="#bottom-nav" className="skip-link">
          Skip to navigation
        </a>
        {children}
        <BottomNav />
      </body>
    </html>
  );
}
