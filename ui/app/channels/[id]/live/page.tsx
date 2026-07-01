"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ControlState } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Section, Spinner, Stat } from "@/components/ui";

const POLL_MS = 4000;

function rel(iso: string | null): string {
  if (!iso) return "—";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  if (s < 86400) return `${Math.round(s / 3600)}h ago`;
  return `${Math.round(s / 86400)}d ago`;
}
function dur(ms: number | null): string {
  if (ms == null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}
// Drop noisy raw IDs (strategy_id: <uuid>, task_id: <uuid>) from summaries/results
// and keep only the human-readable bits.
function clean(s: string | null): string {
  if (!s) return "";
  return s.split(/[·•|]/).map((p) => p.trim())
    .filter((p) => p && !/\b\w*_id\s*:/i.test(p))
    .join(" · ");
}
const STATUS: Record<string, { dot: string; text: string; label: string }> = {
  done: { dot: "bg-green-500", text: "text-green-600", label: "Done" },
  running: { dot: "bg-amber-500 animate-pulse", text: "text-amber-600", label: "Running" },
  failed: { dot: "bg-red-500", text: "text-red-600", label: "Failed" },
  idle: { dot: "bg-slate-300", text: "text-slate-400", label: "Idle" },
};
const HEALTH: Record<string, string> = { green: "bg-green-500", yellow: "bg-amber-500", red: "bg-red-500" };

export default function LivePage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<ControlState | null>(null);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try { setState(await api.control(id)); } catch (e) { setError(String(e)); }
  }, [id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  if (error) return <ErrorBox error={error} />;
  if (!state) return <Spinner />;
  const sys = state.system;

  return (
    <div>
      <PageHeader title="Live status"
        subtitle="Real-time agent pipeline, activity and channel health — updates every 4s."
        actions={
          <span className="inline-flex items-center gap-2 rounded-full border border-edge bg-panel px-3 py-1 text-xs font-medium text-slate-600">
            <span className={`h-2 w-2 rounded-full ${HEALTH[sys.agent_health] || "bg-slate-400"} ${sys.thinking ? "animate-pulse" : ""}`} />
            {sys.thinking ? "Agents working…" : "Idle"}
          </span>
        } />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Subscribers" value={sys.subscriber_count != null ? sys.subscriber_count.toLocaleString() : "—"}
          sub={sys.subscribers_updated_at ? `sampled ${rel(sys.subscribers_updated_at)}` : undefined} />
        <Stat label="Growth rate" value={sys.growth_rate != null ? `${sys.growth_rate >= 0 ? "+" : ""}${sys.growth_rate}%` : "—"} />
        <Stat label="Engagement" value={sys.engagement_pulse != null ? `${sys.engagement_pulse}%` : "—"} />
        <Stat label="Churn risk" value={<span className={sys.churn_risk === "high" ? "text-red-600" : "text-green-600"}>{sys.churn_risk === "high" ? `High${sys.churn_type ? ` · ${sys.churn_type}` : ""}` : "None"}</span>} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Section title="Agent pipeline" desc="Each agent's latest run">
            <div className="space-y-2.5">
              {state.pipeline.map((a) => {
                const st = STATUS[a.status] || STATUS.idle;
                return (
                  <div key={a.agent} className="rounded-lg border border-edge bg-field/40 px-3.5 py-3">
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className="text-base">{a.icon}</span>
                      <span className="text-sm font-semibold text-slate-900">{a.label}</span>
                      <span className={`inline-flex items-center gap-1 text-[11px] font-medium ${st.text}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${st.dot}`} /> {st.label}
                      </span>
                      <span className="ml-auto text-[11px] text-slate-400">{rel(a.last_run)}{a.duration_ms != null ? ` · ${dur(a.duration_ms)}` : ""}</span>
                    </div>
                    {a.steps?.length > 0 && (
                      <div className="mt-2 flex flex-wrap items-center gap-1">
                        {a.steps.map((s, i) => (
                          <span key={i} className="flex items-center gap-1">
                            <span className="rounded bg-white px-1.5 py-0.5 text-[11px] text-slate-600 ring-1 ring-inset ring-slate-200">{s}</span>
                            {i < a.steps.length - 1 && <span className="text-slate-300">→</span>}
                          </span>
                        ))}
                      </div>
                    )}
                    {clean(a.summary) && <p className="mt-2 text-xs leading-relaxed text-slate-500">{clean(a.summary)}</p>}
                  </div>
                );
              })}
            </div>
          </Section>
        </div>

        <Section title="Activity" desc="Recent agent events">
          {state.events.length === 0 ? <EmptyState title="No activity yet" /> : (
            <ol className="space-y-2.5">
              {state.events.slice(0, 12).map((e) => {
                const st = STATUS[e.status] || STATUS.idle;
                return (
                  <li key={e.id} className="flex gap-2.5">
                    <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${st.dot}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-slate-800">{e.icon} {e.label}</span>
                        <span className="text-[11px] text-slate-400">{rel(e.ts)}</span>
                      </div>
                      <p className="truncate text-xs text-slate-500">{clean(e.result) || e.action}{e.reason ? ` — ${e.reason}` : ""}</p>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </Section>
      </div>
    </div>
  );
}
