"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

// Agents that can be triggered standalone (Content runs per-slot via the scheduler,
// so it's excluded here — it needs a strategy_task).
const AGENTS = [
  { key: "onboard", label: "Full pipeline" },
  { key: "dna", label: "Channel DNA" },
  { key: "competitor", label: "Competitor" },
  { key: "analytics", label: "Analytics" },
  { key: "strategy", label: "Strategy" },
];

export function RunAgents({ channelId }: { channelId: string }) {
  const [open, setOpen] = useState(false);
  const [running, setRunning] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDoc(e: MouseEvent) { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  async function run(agent: string, label: string) {
    setRunning((r) => ({ ...r, [agent]: true }));
    setNote("");
    try {
      const res = await api.runAgent(channelId, agent);
      setNote(res.status === "already_running" ? `${label} already running` : `${label} started — see Live`);
    } catch (e) {
      setNote(`Failed: ${String(e).slice(0, 80)}`);
    } finally {
      setTimeout(() => setRunning((r) => ({ ...r, [agent]: false })), 2500);
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 rounded-lg border border-edge bg-panel px-3 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-brand hover:text-brand">
        ⚡ Run agent
        <svg className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>
      </button>
      {open && (
        <div className="absolute right-0 z-30 mt-2 w-56 rounded-xl border border-edge bg-panel p-1.5 shadow-lg">
          {AGENTS.map((a) => (
            <button key={a.key} onClick={() => run(a.key, a.label)} disabled={running[a.key]}
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-50">
              {a.label}
              {running[a.key] && <span className="h-2 w-2 animate-pulse rounded-full bg-green-500" />}
            </button>
          ))}
        </div>
      )}
      {note && <span className="ml-2 text-xs text-slate-500">{note}</span>}
    </div>
  );
}
