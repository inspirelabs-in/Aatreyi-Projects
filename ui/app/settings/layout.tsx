"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function SettingsLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => { api.me().then((m) => setIsAdmin(!!m.is_platform_admin)).catch(() => {}); }, []);

  const tabs = [
    { href: "/settings/profile", label: "User" },
    { href: "/settings", label: "Organization", exact: true },
    { href: "/settings/users", label: "Users" },
    ...(isAdmin ? [{ href: "/admin", label: "Admin" }] : []),
  ];

  return (
    <div>
      <h1 className="mb-4 text-xl font-bold tracking-tight text-slate-900">Settings</h1>
      <div className="mb-6 inline-flex rounded-lg border border-edge bg-field p-1">
        {tabs.map((t) => {
          const active = t.exact ? pathname === t.href : (pathname === t.href || pathname.startsWith(t.href + "/"));
          return (
            <Link key={t.href} href={t.href}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${active ? "bg-white text-brand shadow-sm" : "text-slate-500 hover:text-slate-800"}`}>
              {t.label}
            </Link>
          );
        })}
      </div>
      {children}
    </div>
  );
}
