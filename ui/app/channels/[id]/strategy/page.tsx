"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

export default function StrategyPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Strategy | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.strategy(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  if (error) return <ErrorBox error={error.includes("404") ? "No active strategy yet. Run the strategy agent." : error} />;
  if (!data) return <Spinner />;

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-medium text-slate-900">{data.goal}</div>
            <div className="text-xs text-slate-500">{data.period_start} → {data.period_end} · {data.post_frequency_per_day} posts/day</div>
          </div>
          <Badge tone="blue">{data.strategy_type}</Badge>
        </div>
        {data.diagnosis && (
          <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-700">
            <span className="font-medium text-slate-500">Diagnosis: </span>{data.diagnosis}
          </p>
        )}
        {data.benchmark && data.benchmark.competitor_avg_er != null && (
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            <Badge tone="slate">your ER {data.benchmark.my_avg_er ?? "—"}%</Badge>
            <Badge tone="amber">competitor avg {data.benchmark.competitor_avg_er}%</Badge>
            <Badge tone="green">target {data.benchmark.target_er ?? "—"}%</Badge>
          </div>
        )}
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Content mix">
          <div className="space-y-2">
            {(data.content_mix || []).map((m) => (
              <div key={m.format}>
                <div className="flex justify-between text-sm text-slate-700"><span className="capitalize">{m.format}</span><span className="font-medium text-slate-900">{m.pct}%</span></div>
                <div className="mt-1 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-brand" style={{ width: `${m.pct}%` }} /></div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Focus topics">
          <div className="flex flex-wrap gap-2">
            {(data.primary_topics || []).map((t) => <Badge key={t} tone="green">{t}</Badge>)}
          </div>
        </Card>
      </div>

      <Card title="🧠 Why this plan — diagnosis &amp; actions">
        {(data.growth_tactics || []).length === 0 ? (
          <p className="text-sm text-slate-500">No issues detected — the channel is healthy; hold the current plan.</p>
        ) : (
          <ul className="space-y-3">
            {(data.growth_tactics || []).map((g, i) => {
              const sev = g.severity === "high" ? "red" : g.severity === "medium" ? "amber" : "slate";
              return (
                <li key={i} className="rounded-lg border border-edge bg-white p-3">
                  <div className="flex items-center gap-2">
                    <Badge tone={sev as "red" | "amber" | "slate"}>{g.severity || "info"}</Badge>
                    <span className="text-sm font-semibold text-slate-800">{g.tactic.replace(/_/g, " ")}</span>
                  </div>
                  {g.why && <p className="mt-2 text-sm text-slate-600"><span className="font-medium text-slate-500">Why: </span>{g.why}</p>}
                  <p className="mt-1 text-sm text-slate-700"><span className="font-medium text-slate-500">Action: </span>{g.action || g.detail}</p>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      <Card title={`Post slots (${data.tasks.length})`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr><th className="py-2">Date</th><th>Time</th><th>Format</th><th>Topic</th><th>Status</th></tr>
            </thead>
            <tbody>
              {data.tasks.map((t) => (
                <tr key={t.task_id} className="border-t border-edge">
                  <td className="py-2">{t.date}</td>
                  <td>{t.time?.slice(0, 5)}</td>
                  <td><Badge>{t.format}</Badge></td>
                  <td>{t.kind ? <><Badge tone="blue">{t.kind}</Badge> {t.topic}</> : t.topic}</td>
                  <td><Badge tone="amber">{t.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
