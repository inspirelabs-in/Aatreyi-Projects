"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { AdminOverview, GlobalEvent } from "@/lib/types";
import { Card, ErrorBox, Spinner, Stat } from "@/components/ui";

const POLL_MS = 5000;
const DOT: Record<string, string> = { done: "bg-green-500", running: "bg-blue-500 animate-pulse", failed: "bg-red-500", idle: "bg-slate-300" };

function ago(ts: string | null) {
  if (!ts) return "—";
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

export default function GlobalControlRoom() {
  const [ov, setOv] = useState<AdminOverview | null>(null);
  const [events, setEvents] = useState<GlobalEvent[] | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const [o, e] = await Promise.all([api.adminOverview(), api.adminEvents(60)]);
      setOv(o); setEvents(e); setError("");
    } catch (e) { setError(String(e)); }
  }, []);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  if (error && !ov) return <ErrorBox error={error} />;
  if (!ov || !events) return <Spinner label="Loading global control room…" />;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2">
        <h1 className="text-xl font-semibold text-slate-900">🛰️ Global Control Room</h1>
        <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" /> live · all tenants
        </span>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Stat label="Channels" value={ov.channels} />
        <Stat label="Agent runs" value={ov.agent_runs} />
        <Stat label="Success rate" value={ov.success_rate != null ? `${ov.success_rate}%` : "—"} />
        <Stat label="Running now" value={ov.running_now} />
        <Stat label="Pending review" value={ov.pending_review} />
      </div>

      <Card title="Live agent stream — all channels">
        <div className="space-y-2">
          {events.length === 0 && <p className="text-sm text-slate-400">No activity yet.</p>}
          {events.map((e) => (
            <div key={e.id} className="flex items-start gap-2 rounded-lg border border-edge bg-white p-2.5">
              <span className="text-base leading-none">{e.icon}</span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-slate-800">{e.label}</span>
                  {e.channel && <span className="truncate text-xs text-brand">@{e.channel}</span>}
                  <span className={`ml-auto h-1.5 w-1.5 rounded-full ${DOT[e.status] ?? "bg-slate-300"}`} />
                  <span className="text-[11px] text-slate-400">{ago(e.ts)} ago</span>
                </div>
                <div className="text-sm text-slate-600">{e.action}{e.result ? ` — ${e.result}` : ""}</div>
                {e.reason && <div className="text-xs text-red-600">⚠ {e.reason}</div>}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
