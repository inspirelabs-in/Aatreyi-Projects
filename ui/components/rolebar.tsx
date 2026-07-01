"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { getActingUser, setActingUser } from "@/lib/currentUser";

const USER_NAV = [
  { href: "/", label: "My Channels" },
  { href: "/settings", label: "Settings" },
  { href: "/settings/users", label: "Users" },
];
const ADMIN_NAV = [
  { href: "/admin", label: "Global Control Room" },
  { href: "/admin/channels", label: "All Channels" },
  { href: "/admin/health", label: "System Health" },
  { href: "/admin/performance", label: "Agent Performance" },
  { href: "/organizations", label: "Organizations" },
  { href: "/organizations/new", label: "New Org" },
  { href: "/settings/users", label: "Users" },
];

export function RoleBar() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [users, setUsers] = useState<User[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [isAdmin, setIsAdmin] = useState(true);

  useEffect(() => {
    const acting = getActingUser();
    setEmail(acting.email);
    setIsAdmin(acting.is_admin);
    setMounted(true);
    api.usersList().then(setUsers).catch(() => setUsers([]));
  }, []);

  function switchTo(u: User) {
    setActingUser({ email: u.email, is_admin: u.is_admin, name: u.name });
    setEmail(u.email);
    setIsAdmin(u.is_admin);
    router.push(u.is_admin ? "/admin" : "/");
    router.refresh();
  }

  const nav = isAdmin ? ADMIN_NAV : USER_NAV;
  // The currently-selected identity (fall back to the first admin when unset).
  const current = users.find((u) => u.email && u.email === email)
    || users.find((u) => u.is_admin) || null;

  return (
    <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
      <Link href={isAdmin ? "/admin" : "/"} className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand text-sm font-bold text-white shadow-sm">G</span>
        <span className="text-base font-bold tracking-tight text-slate-900">GrowthOS</span>
      </Link>

      {mounted && (
        <nav className="flex flex-wrap items-center gap-1">
          {nav.map((n) => {
            const active = pathname === n.href || (n.href !== "/" && pathname.startsWith(n.href));
            return (
              <Link key={n.href} href={n.href}
                className={`rounded-md px-2.5 py-1 text-sm transition ${active ? "bg-blue-50 font-medium text-brand" : "text-slate-500 hover:text-slate-900"}`}>
                {n.label}
              </Link>
            );
          })}
        </nav>
      )}

      {mounted && (
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400">Signed in as</span>
          <select
            value={current?.id ?? ""}
            onChange={(e) => {
              const u = users.find((x) => x.id === e.target.value);
              if (u) switchTo(u);
            }}
            className="max-w-[16rem] rounded-md border border-edge bg-white px-2.5 py-1 text-xs font-medium text-slate-700 outline-none focus:border-brand"
          >
            {users.length === 0 && <option value="">Loading…</option>}
            {users.map((u) => (
              <option key={u.id} value={u.id} disabled={!u.email}>
                {u.is_admin ? "★ " : ""}{u.name} · {u.org_slug}{u.email ? "" : " (no email)"}
              </option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
