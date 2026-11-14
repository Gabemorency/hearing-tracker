import type { Metadata } from "next";
import { Playfair_Display, IBM_Plex_Sans, IBM_Plex_Mono } from "next/font/google";
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

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${playfair.variable} ${plexSans.variable} ${plexMono.variable}`}>
        {children}
      </body>
    </html>
  );
}
