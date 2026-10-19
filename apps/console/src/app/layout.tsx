import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Triage Console",
  description: "Admin dashboard for AI-powered support triage",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <span className="app-title">Triage Console</span>
        </header>
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
