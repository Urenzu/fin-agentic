import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "fin-agentic",
  description: "Verified financial statement analysis from SEC filings",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="h-full overflow-hidden bg-void text-ink">{children}</body>
    </html>
  );
}
