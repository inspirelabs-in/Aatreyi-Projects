"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

const TABS = [
  { slug: "", label: "🧠 Control Room" },
  { slug: "queue", label: "Content Factory" },
  { slug: "sources", label: "Sources" },
  { slug: "intelligence", label: "Intelligence" },
  { slug: "analytics", label: "Analytics" },
  { slug: "strategy", label: "Strategy" },
  { slug: "competitors", label: "Competitors" },
];

export default function ChannelLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const base = `/channels/${id}`;
  const [running, setRunning] = useState("");
  const [msg, setMsg] = useState("");

  async function run(agent: string) {
    setRunning(agent); setMsg("");
    try {
      await api.runAgent(id, agent, agent === "analytics" ? { snapshot_type: "daily" } : {});
      setMsg(`${agent} ✓ — refresh to see updates`);
    } catch (e) {
      setMsg(`${agent} failed: ${String(e)}`);
    } finally {
      setRunning("");
    }
  }

  return (
    <div className="space-y-4">
      <Link href="/" className="text-sm text-slate-500 transition hover:text-slate-900">← all channels</Link>

      <nav className="flex flex-wrap gap-1 border-b border-edge">
        {TABS.map((t) => {
          const href = t.slug ? `${base}/${t.slug}` : base;
          const active = pathname === href;
          return (
            <Link key={t.slug} href={href}
              className={`px-4 py-2 text-sm transition ${active ? "-mb-px border-b-2 border-brand font-medium text-brand" : "text-slate-500 hover:text-slate-900"}`}>
              {t.label}
            </Link>
          );
        })}
      </nav>

      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-slate-500">Run agent:</span>
        {["onboard", "dna", "competitor", "analytics", "strategy"].map((a) => (
          <button key={a} onClick={() => run(a)} disabled={!!running}
            className="rounded-md border border-edge bg-panel px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm transition hover:border-brand hover:text-brand disabled:opacity-50">
            {running === a ? `${a}…` : a}
          </button>
        ))}
        {msg && <span className="text-xs text-slate-500">{msg}</span>}
      </div>

      {children}
    </div>
  );
}
