import type { Metadata } from "next";
import "./globals.css";
import { BRAND } from "@/lib/brand";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: `${BRAND.name} — ${BRAND.tagline}`,
  description: BRAND.blurb,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
