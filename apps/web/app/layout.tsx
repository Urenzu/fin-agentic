import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";

/**
 * Self-hosted at build time by next/font, so there is no CDN request and no
 * flash of fallback text.
 *
 * The system stack resolved to Segoe UI on Windows, which sets numerals with
 * old-style proportions and a wide, soft `1`. Inter was drawn for interfaces,
 * has true tabular figures, and holds its shape at the 10px the section
 * headings need.
 */
const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

/**
 * Figures only. A statement is read down a column, and a monospaced face makes
 * the digits a fixed rhythm regardless of value -- the same reason annual
 * reports are typeset this way.
 *
 * Plex rather than JetBrains Mono: the latter sets a dotted zero, which is a
 * code-editor convention. In a column of financial figures it reads as a
 * printing artefact on the page.
 */
const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  display: "swap",
  weight: ["400", "500", "600"],
  variable: "--font-mono-figures",
});

export const metadata: Metadata = {
  title: "fin-agentic",
  description: "Verified financial statement analysis from SEC filings",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body className="h-full overflow-hidden bg-void text-ink antialiased">{children}</body>
    </html>
  );
}
