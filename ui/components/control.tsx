"use client";

import React, { useState } from "react";
import type { AgentEvent, PipelineAgent, SystemState } from "@/lib/types";

// ── shared bits ──────────────────────────────────────────────────────────────
const STATUS_DOT: Record<string, string> = {
  done: "bg-green-500",
  running: "bg-blue-500 animate-pulse",
  failed: "bg-red-500",
  idle: "bg-slate-300",
};

function ago(ts: string | null): string {
  if (!ts) return "—";
  const s = Math.max(0, (Date.now() - new Date(ts).getTime()) / 1000);
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function dur(ms: number | null): string {
  if (ms == null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

// ── LEFT: live agent stream ───────────────────────────────────────────────────
export function AgentStream({ events }: { events: AgentEvent[] }) {
  return (
    <div className="flex h-full flex-col rounded-xl border border-edge bg-panel shadow-card">
      <div className="flex items-center gap-2 border-b border-edge px-4 py-3">
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-green-400 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-green-500" />
        </span>
        <h3 className="text-sm font-semibold text-slate-700">Live Agent Stream</h3>
      </div>
      <div className="flex-1 space-y-2 overflow-y-auto p-3" style={{ maxHeight: "70vh" }}>
        {events.length === 0 && <p className="py-8 text-center text-sm text-slate-400">No agent activity yet.</p>}
        {events.map((e) => (
          <div key={e.id} className="rounded-lg border border-edge bg-white p-2.5">
            <div className="flex items-center gap-2">
              <span className="text-base leading-none">{e.icon}</span>
              <span className="text-sm font-medium text-slate-800">{e.label} Agent</span>
              <span className={`ml-auto h-1.5 w-1.5 rounded-full ${STATUS_DOT[e.status] ?? "bg-slate-300"}`} />
              <span className="text-[11px] text-slate-400">{ago(e.ts)}</span>
            </div>
            <div className="mt-1 text-sm text-slate-600">
              {e.action}{e.result ? ` — ${e.result}` : ""}
            </div>
            {e.reason && <div className="mt-1 text-xs text-red-600">⚠ {e.reason}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── CENTER: workflow pipeline visualizer ──────────────────────────────────────
export function PipelineFlow({ pipeline, onCancel }: { pipeline: PipelineAgent[]; onCancel?: (agent: string) => void }) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-slate-700">Active Agent Workflows</h3>
      {pipeline.map((p) => <PipelineCard key={p.agent} p={p} onCancel={onCancel} />)}
    </div>
  );
}

function PipelineCard({ p, onCancel }: { p: PipelineAgent; onCancel?: (agent: string) => void }) {
  const [open, setOpen] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const tone: Record<string, string> = {
    done: "border-green-200",
    running: "border-blue-300 ring-1 ring-blue-200",
    failed: "border-red-200",
    idle: "border-edge",
  };

  async function handleCancel(e: React.MouseEvent) {
    e.stopPropagation();
    setCancelling(true);
    try { await onCancel?.(p.agent); } finally { setCancelling(false); }
  }

  return (
    <div className={`rounded-xl border bg-panel p-4 shadow-card ${tone[p.status] ?? "border-edge"}`}>
      <div className="flex w-full items-center gap-2">
        <button onClick={() => setOpen(!open)} className="flex flex-1 items-center gap-2 text-left">
          <span className="text-lg leading-none">{p.icon}</span>
          <span className="font-medium text-slate-800">{p.label} Flow</span>
          <span className={`h-2 w-2 rounded-full ${STATUS_DOT[p.status] ?? "bg-slate-300"}`} />
          <span className="text-xs capitalize text-slate-500">{p.status}</span>
          <span className="ml-auto text-xs text-slate-400">
            {p.last_run ? `${ago(p.last_run)}${p.duration_ms != null ? ` · ${dur(p.duration_ms)}` : ""}` : "never run"}
          </span>
        </button>
        {p.status === "running" && onCancel && (
          <button
            onClick={handleCancel}
            disabled={cancelling}
            className="rounded-md border border-red-200 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-600 transition hover:bg-red-100 disabled:opacity-50"
          >
            {cancelling ? "Stopping…" : "Stop"}
          </button>
        )}
      </div>

      {/* step chain */}
      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {p.steps.map((s, i) => (
          <React.Fragment key={s}>
            <span className={`rounded-md px-2 py-1 text-xs ${
              p.status === "done" ? "bg-green-50 text-green-700"
              : p.status === "running" ? "bg-blue-50 text-blue-700"
              : p.status === "failed" ? "bg-red-50 text-red-700"
              : "bg-slate-100 text-slate-500"
            }`}>{s}</span>
            {i < p.steps.length - 1 && <span className="text-slate-300">→</span>}
          </React.Fragment>
        ))}
      </div>

      {open && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
          <div className="font-medium text-slate-500">Last output</div>
          <div className="mt-1 whitespace-pre-wrap">{p.summary || "—"}</div>
        </div>
      )}
    </div>
  );
}

// ── RIGHT: system state + mini analytics + triggers ────────────────────────────
const TREND_ICON: Record<string, string> = { up: "▲", down: "▼", flat: "▬" };
const TREND_COLOR: Record<string, string> = { up: "text-green-600", down: "text-red-600", flat: "text-slate-500" };
const HEALTH: Record<string, { dot: string; label: string }> = {
  green: { dot: "bg-green-500", label: "All systems healthy" },
  yellow: { dot: "bg-amber-500", label: "Recovered from a failure" },
  red: { dot: "bg-red-500", label: "An agent is failing" },
};

export function SystemPanel({
  system, channelId, onRun, running,
}: {
  system: SystemState;
  channelId: string;
  onRun: (agent: string) => void;
  running: string;
}) {
  const h = HEALTH[system.agent_health] ?? HEALTH.green;
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-edge bg-panel p-4 shadow-card">
        <div className="flex items-center gap-2">
          <span className={`h-2.5 w-2.5 rounded-full ${h.dot}`} />
          <span className="text-sm font-semibold text-slate-700">System State</span>
          {system.thinking && (
            <span className="ml-auto flex items-center gap-1 text-xs text-blue-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500" /> thinking…
            </span>
          )}
        </div>
        <p className="mt-1 text-xs text-slate-500">{h.label}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Metric label="Growth rate" value={system.growth_rate != null ? `${system.growth_rate > 0 ? "+" : ""}${system.growth_rate}%` : "—"}
          tone={(system.growth_rate ?? 0) >= 0 ? "text-green-600" : "text-red-600"} />
        <Metric label="Engagement pulse" value={system.engagement_pulse != null ? `${system.engagement_pulse}%` : "—"} />
        <Metric label="Retention" value={`${TREND_ICON[system.retention_trend] ?? "▬"} ${system.retention_trend}`}
          tone={TREND_COLOR[system.retention_trend] ?? "text-slate-500"} />
        <Metric label="Churn risk"
          value={system.churn_risk === "unknown" ? "no data yet" : system.churn_risk + (system.churn_type ? ` · ${system.churn_type}` : "")}
          tone={system.churn_risk === "high" ? "text-red-600" : system.churn_risk === "medium" ? "text-amber-600" : system.churn_risk === "low" ? "text-amber-500" : system.churn_risk === "unknown" ? "text-slate-400" : "text-green-600"} />
      </div>

      <div className="rounded-xl border border-edge bg-panel p-4 shadow-card">
        <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Manual triggers</div>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {["dna", "competitor", "analytics", "strategy"].map((a) => (
            <button key={a} onClick={() => onRun(a)} disabled={!!running}
              className="rounded-md border border-edge bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm transition hover:border-brand hover:text-brand disabled:opacity-50">
              {running === a ? `${a}…` : `Run ${a}`}
            </button>
          ))}
        </div>
        <p className="mt-2 text-[11px] text-slate-400">
          Subscribers: {system.subscriber_count?.toLocaleString() ?? "—"}
          {system.subscribers_updated_at && <> · sampled {ago(system.subscribers_updated_at)} ago</>}
        </p>
      </div>
    </div>
  );
}

function Metric({ label, value, tone = "text-slate-900" }: { label: string; value: React.ReactNode; tone?: string }) {
  return (
    <div className="rounded-xl border border-edge bg-panel p-3 shadow-card">
      <div className="text-[11px] uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold capitalize ${tone}`}>{value}</div>
    </div>
  );
}
