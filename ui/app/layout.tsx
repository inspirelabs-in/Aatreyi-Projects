import type { Metadata } from "next";
import "./globals.css";
import { RoleBar } from "@/components/rolebar";

export const metadata: Metadata = {
  title: "GrowthOS — Agent Control Room",
  description: "Live AI agents for Telegram growth & retention",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="sticky top-0 z-10 border-b border-edge bg-white/80 backdrop-blur">
          <RoleBar />
        </header>
        <main className="mx-auto max-w-6xl px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
