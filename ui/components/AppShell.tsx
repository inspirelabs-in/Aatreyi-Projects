"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { RequireAuth } from "@/components/RequireAuth";

// Public routes render bare (no sidebar, no auth gate).
const PUBLIC = new Set(["/", "/login"]);

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  if (PUBLIC.has(pathname)) return <>{children}</>;

  return (
    <RequireAuth>
      <div className="min-h-screen bg-ink">
        <Sidebar />
        <main className="ml-60 min-h-screen">
          <div className="mx-auto max-w-6xl px-6 py-6">{children}</div>
        </main>
      </div>
    </RequireAuth>
  );
}
