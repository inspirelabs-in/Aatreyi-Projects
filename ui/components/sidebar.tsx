"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChannelSummary, User } from "@/lib/types";
import { getActingUser, setActingUser } from "@/lib/currentUser";
import { logout } from "@/lib/auth";
import { Logo } from "@/components/Logo";

// Minimal inline line-icons (keeps the bundle tiny, look consistent).
const ICONS: Record<string, string> = {
  channels: "M4 6h16M4 12h16M4 18h16",
  orgs: "M3 21h18M6 21V7l6-4 6 4v14M9 9h.01M9 13h.01M9 17h.01",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.7 1.7 0 00.3 1.9l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-2.9 1.2 2 2 0 11-4 0 1.7 1.7 0 00-2.9-1.2l-.1.1a2 2 0 11-2.8-2.8l.1-.1A1.7 1.7 0 004.6 15a2 2 0 110-4 1.7 1.7 0 001.5-2.9l-.1-.1A2 2 0 118.8 5.2l.1.1a1.7 1.7 0 002.9-1.2 2 2 0 014 0 1.7 1.7 0 002.9 1.2l.1-.1a2 2 0 112.8 2.8l-.1.1A1.7 1.7 0 0019.4 11a2 2 0 110 4z",
  admin: "M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7l8-4z",
  dashboard: "M4 13h6V4H4v9zm10 7h6V4h-6v16zM4 20h6v-5H4v5z",
  strategy: "M3 3v18h18M7 15l4-4 3 3 5-6",
  content: "M4 5h16M4 5v14a1 1 0 001 1h14a1 1 0 001-1V5M8 9h8M8 13h5",
  intelligence: "M9 3a4 4 0 00-4 4c0 1 .3 1.8.8 2.5A4 4 0 007 16a3 3 0 003 3V3H9zM15 3a4 4 0 014 4c0 1-.3 1.8-.8 2.5A4 4 0 0117 16a3 3 0 01-3 3V3h1z",
  competitors: "M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2M9 11a4 4 0 100-8 4 4 0 000 8zM22 21v-2a4 4 0 00-3-3.9M16 3.1a4 4 0 010 7.8",
  live: "M12 12m-2 0a2 2 0 104 0 2 2 0 10-4 0M5 12a7 7 0 0114 0M2 12a10 10 0 0120 0",
  logout: "M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9",
};
function Icon({ name, className = "" }: { name: string; className?: string }) {
  return (
    <svg className={`h-[18px] w-[18px] flex-shrink-0 ${className}`} viewBox="0 0 24 24" fill="none"
         stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d={ICONS[name]} />
    </svg>
  );
}

const WORKSPACE = [
  { slug: "", label: "Dashboard", icon: "dashboard" },
  { slug: "strategy", label: "Strategy", icon: "strategy" },
  { slug: "queue", label: "Content", icon: "content" },
  { slug: "intelligence", label: "Intelligence", icon: "intelligence" },
  { slug: "competitors", label: "Competitors", icon: "competitors" },
  { slug: "live", label: "Live", icon: "live" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<{ email: string | null; is_admin: boolean; name?: string | null }>({ email: null, is_admin: true });
  const [users, setUsers] = useState<User[]>([]);
  const [channels, setChannels] = useState<ChannelSummary[]>([]);

  useEffect(() => {
    setMe(getActingUser());
    api.usersList().then(setUsers).catch(() => setUsers([]));
    api.listChannels().then(setChannels).catch(() => setChannels([]));
  }, [pathname]);

  const m = pathname.match(/^\/channels\/([^/]+)/);
  const channelId = m?.[1] && m[1] !== "" ? m[1] : null;
  const channel = channelId ? channels.find((c) => c.id === channelId) : null;

  function switchUser(u: User) {
    setActingUser({ email: u.email, is_admin: u.is_admin, name: u.name });
    setMe({ email: u.email, is_admin: u.is_admin, name: u.name });
    router.refresh();
  }
  function onLogout() { logout(); router.replace("/login"); }

  const NavLink = ({ href, icon, label, exact = false }: { href: string; icon: string; label: string; exact?: boolean }) => {
    const active = exact ? pathname === href : (pathname === href || pathname.startsWith(href + "/"));
    return (
      <Link href={href}
        className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition ${
          active ? "bg-blue-50 font-medium text-brand" : "text-slate-600 hover:bg-slate-50 hover:text-slate-900"
        }`}>
        <Icon name={icon} /> {label}
      </Link>
    );
  };

  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-60 flex-col border-r border-edge bg-panel">
      <div className="flex h-16 items-center px-5">
        <Link href="/channels"><Logo size={30} /></Link>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        <NavLink href="/channels" icon="channels" label="Channels" exact />
        <NavLink href="/organizations" icon="orgs" label="Organizations" />
        <NavLink href="/settings" icon="settings" label="Settings" />
        {me.is_admin && <NavLink href="/admin" icon="admin" label="Admin" />}

        {channelId && (
          <div className="mt-4">
            <div className="flex items-center justify-between px-3 pb-1">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Workspace</span>
            </div>
            {channel && (
              <div className="truncate px-3 pb-2 text-xs font-medium text-slate-500">@{channel.telegram_username}</div>
            )}
            <div className="space-y-1">
              {WORKSPACE.map((w) => (
                <NavLink key={w.slug} icon={w.icon} label={w.label} exact={w.slug === ""}
                  href={`/channels/${channelId}${w.slug ? "/" + w.slug : ""}`} />
              ))}
            </div>
          </div>
        )}
      </nav>

      <div className="border-t border-edge p-3">
        <label className="mb-1 block text-[11px] font-medium uppercase tracking-wider text-slate-400">Signed in as</label>
        <select
          value={users.find((u) => u.email && u.email === me.email)?.id ?? ""}
          onChange={(e) => { const u = users.find((x) => x.id === e.target.value); if (u) switchUser(u); }}
          className="mb-2 w-full rounded-md border border-edge bg-field px-2 py-1.5 text-xs text-slate-700 outline-none focus:border-brand">
          {users.length === 0 && <option value="">{me.name || me.email || "Admin"}</option>}
          {users.map((u) => (
            <option key={u.id} value={u.id} disabled={!u.email}>
              {u.is_admin ? "★ " : ""}{u.name} · {u.org_slug}
            </option>
          ))}
        </select>
        <button onClick={onLogout}
          className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-600 transition hover:bg-slate-50 hover:text-red-600">
          <Icon name="logout" /> Log out
        </button>
      </div>
    </aside>
  );
}
