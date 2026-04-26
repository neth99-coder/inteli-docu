import type { Metadata } from "next";
import { IBM_Plex_Serif, Manrope } from "next/font/google";

import "./globals.css";

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-sans",
});

const ibmPlexSerif = IBM_Plex_Serif({
  subsets: ["latin"],
  variable: "--font-serif",
  weight: ["400", "600"],
});

export const metadata: Metadata = {
  title: "Document Intelligence for Accountants",
  description: "Stage 1 MVP for page-by-page accountant-focused document summaries.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${manrope.variable} ${ibmPlexSerif.variable}`}>
        <div className="site-shell">
          <div className="site-main">{children}</div>
          <footer className="site-footer">made with ❤️ by N3TH.</footer>
        </div>
      </body>
    </html>
  );
}
