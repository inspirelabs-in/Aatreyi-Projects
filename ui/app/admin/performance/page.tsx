"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AgentPerf } from "@/lib/types";
import { Card, ErrorBox, Spinner } from "@/components/ui";

export default function AgentPerformance() {
  const [rows, setRows] = useState<AgentPerf[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.adminPerformance().then(setRows).catch((e) => setError(String(e))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!rows) return <Spinner />;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">Agent Performance <span className="text-sm font-normal text-slate-500">(across all tenants)</span></h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((a) => {
          const rate = a.success_rate;
          const tone = rate == null ? "text-slate-400" : rate >= 90 ? "text-green-600" : rate >= 70 ? "text-amber-600" : "text-red-600";
          return (
            <Card key={a.agent}>
              <div className="flex items-center gap-2">
                <span className="text-lg">{a.icon}</span>
                <span className="font-medium text-slate-800">{a.label}</span>
              </div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                <div><div className="text-lg font-semibold text-slate-900">{a.runs}</div><div className="text-[11px] uppercase text-slate-400">runs</div></div>
                <div><div className={`text-lg font-semibold ${tone}`}>{rate != null ? `${rate}%` : "—"}</div><div className="text-[11px] uppercase text-slate-400">success</div></div>
                <div><div className="text-lg font-semibold text-slate-900">{a.avg_ms != null ? `${(a.avg_ms / 1000).toFixed(1)}s` : "—"}</div><div className="text-[11px] uppercase text-slate-400">avg time</div></div>
              </div>
              {a.failed > 0 && <div className="mt-2 text-xs text-red-600">{a.failed} failed run{a.failed > 1 ? "s" : ""}</div>}
            </Card>
          );
        })}
      </div>
    </div>
  );
}
