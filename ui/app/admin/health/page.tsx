"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { SystemHealth } from "@/lib/types";
import { Card, ErrorBox, Spinner } from "@/components/ui";

const HEALTH_DOT: Record<string, string> = { green: "bg-green-500", yellow: "bg-amber-500", red: "bg-red-500" };

export default function SystemHealthPage() {
  const [data, setData] = useState<SystemHealth | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.adminHealth().then(setData).catch((e) => setError(String(e))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">System Health</h1>

      <Card title="Per-channel agent health">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {data.channel_health.map((c) => (
            <div key={c.channel_id} className="flex items-center gap-2 rounded-lg border border-edge bg-white p-3">
              <span className={`h-2.5 w-2.5 rounded-full ${HEALTH_DOT[c.health] ?? "bg-slate-300"}`} />
              <span className="font-medium text-slate-800">@{c.channel}</span>
              <span className="ml-auto text-xs text-slate-400">{c.runs} runs</span>
            </div>
          ))}
          {data.channel_health.length === 0 && <p className="text-sm text-slate-400">No channels.</p>}
        </div>
      </Card>

      <Card title={`Recent failures (${data.recent_failures.length})`}>
        {data.recent_failures.length === 0 ? (
          <p className="text-sm text-green-600">✓ No recent agent failures across any tenant.</p>
        ) : (
          <ul className="space-y-2">
            {data.recent_failures.map((f, i) => (
              <li key={i} className="rounded-lg border border-red-200 bg-red-50 p-2.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-red-700">{f.agent}</span>
                  {f.channel && <span className="text-xs text-slate-500">@{f.channel}</span>}
                  <span className="ml-auto text-[11px] text-slate-400">{f.ts?.slice(0, 19).replace("T", " ")}</span>
                </div>
                <div className="mt-1 text-xs text-red-600">{f.error}</div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
