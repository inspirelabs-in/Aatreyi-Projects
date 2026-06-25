"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getRole, setRole, type Role } from "@/lib/role";

const USER_NAV = [{ href: "/", label: "My Channels" }];
const ADMIN_NAV = [
  { href: "/admin", label: "Global Control Room" },
  { href: "/admin/channels", label: "All Channels" },
  { href: "/admin/health", label: "System Health" },
  { href: "/admin/performance", label: "Agent Performance" },
];

export function RoleBar() {
  const router = useRouter();
  const pathname = usePathname();
  const [role, setRoleState] = useState<Role>("user");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setRoleState(getRole());
    setMounted(true);
  }, []);

  function switchTo(r: Role) {
    setRole(r);
    setRoleState(r);
    router.push(r === "admin" ? "/admin" : "/");
    router.refresh();
  }

  const nav = role === "admin" ? ADMIN_NAV : USER_NAV;

  return (
    <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-6 py-3">
      <Link href={role === "admin" ? "/admin" : "/"} className="text-lg font-semibold text-slate-900">
        🧠 GrowthOS
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
          <span className="text-xs text-slate-400">Viewing as</span>
          <div className="flex overflow-hidden rounded-md border border-edge">
            {(["user", "admin"] as Role[]).map((r) => (
              <button key={r} onClick={() => switchTo(r)}
                className={`px-2.5 py-1 text-xs font-medium capitalize transition ${
                  role === r ? "bg-brand text-white" : "bg-white text-slate-600 hover:bg-slate-50"
                }`}>
                {r}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
