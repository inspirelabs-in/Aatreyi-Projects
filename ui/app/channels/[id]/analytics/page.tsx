"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/lib/api";
import type { AnalyticsPoint, SubscriberPoint } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

type TimelineEntry = { date: string; type: string; note: string };

function buildTimeline(data: AnalyticsPoint[]): TimelineEntry[] {
  const out: TimelineEntry[] = [];
  for (const d of [...data].reverse()) {
    const date = d.period_end ?? "";
    if (d.churn_signal) out.push({ date, type: "churn", note: "Analytics Agent detected a churn signal" });
    for (const i of d.insights || []) out.push({ date, type: i.type, note: i.note });
  }
  return out.slice(0, 12);
}

export default function AnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AnalyticsPoint[] | null>(null);
  const [subs, setSubs] = useState<SubscriberPoint[]>([]);
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    api.analytics(id, "daily", 30).then(setData).catch((e) => setError(String(e)));
    api.subscribers(id).then(setSubs).catch(() => {});
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  if (data.length === 0) return <p className="text-slate-500">No analytics snapshots yet. Run the analytics agent.</p>;

  const chart = data.map((d) => ({
    date: d.period_end?.slice(5) ?? "",
    er: d.avg_er ?? 0,
  }));
  // real subscriber samples (every ~20 min) — the live, updating growth series
  const subChart = subs
    .filter((s) => s.subscriber_count != null)
    .map((s) => ({
      t: s.ts ? new Date(s.ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "",
      subscribers: s.subscriber_count,
    }));

  const timeline = buildTimeline(data);
  const hasErData = chart.some((d) => d.er > 0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">What the agents discovered</h1>
        <p className="text-sm text-slate-500">Analytics is a byproduct of agent execution — these are the signals the Analytics Agent surfaced and the Strategy Agent acts on.</p>
      </div>

      <Card title="Insight timeline">
        {timeline.length === 0 ? (
          <p className="text-sm text-slate-500">No agent insights yet. Run the Analytics agent.</p>
        ) : (
          <ul className="space-y-3">
            {timeline.map((t, i) => (
              <li key={i} className="flex items-start gap-3">
                <div className="mt-0.5 flex flex-col items-center">
                  <span className={`h-2.5 w-2.5 rounded-full ${t.type === "churn" || t.type === "er_drop" ? "bg-red-500" : "bg-green-500"}`} />
                  {i < timeline.length - 1 && <span className="mt-1 h-6 w-px bg-edge" />}
                </div>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <Badge tone={t.type === "churn" || t.type === "er_drop" ? "red" : "green"}>{t.type}</Badge>
                    <span className="text-xs text-slate-400">{t.date}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{t.note}</p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="pt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Supporting visuals (agent-derived)</p>

      <Card title="Subscriber growth (live - sampled every ~20 min)">
        {!mounted || subChart.length === 0 ? (
          <p className="text-sm text-slate-500">
            Collecting live subscriber samples... the poller records the count every ~20 min.
            Telegram does not expose historical counts, so this chart builds up from now.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={256}>
            <LineChart data={subChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="t" stroke="#94a3b8" fontSize={11} />
              <YAxis stroke="#94a3b8" fontSize={12} domain={["auto", "auto"]} width={60} />
              <Tooltip contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, color: "#0f172a" }} />
              <Line type="monotone" dataKey="subscribers" stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Card title="Engagement rate (%)">
        {!mounted ? null : !hasErData ? (
          <p className="text-sm text-slate-500">
            No engagement rate data yet — the Analytics agent needs at least one run with real post data.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={224}>
            <LineChart data={chart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} width={48} domain={[0, "dataMax + 0.5"]} />
              <Tooltip
                formatter={(v: number) => [`${v.toFixed(3)}%`, "ER"]}
                contentStyle={{ background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, color: "#0f172a" }}
              />
              <Line type="monotone" dataKey="er" stroke="#16a34a" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      <Card title="Snapshots">
        {(() => {
          const rows = [...data].reverse();
          const hasSubs = data.some((d) => d.subscriber_count != null);
          const hasChurn = data.some((d) => d.churn_signal);
          const num = "px-3 py-2 text-right tabular-nums";
          return (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-wide text-slate-500">
                    <tr className="border-b border-edge">
                      <th className="py-2 pr-3 text-left">Date</th>
                      {hasSubs && <th className="px-3 py-2 text-right">Subs</th>}
                      {hasSubs && <th className="px-3 py-2 text-right">Delta</th>}
                      <th className="px-3 py-2 text-right">Views</th>
                      <th className="px-3 py-2 text-right">ER</th>
                      <th className="px-3 py-2 text-right">Posts</th>
                      {hasChurn && <th className="px-3 py-2 text-right">Churn</th>}
                    </tr>
                  </thead>
                  <tbody className="text-slate-700">
                    {rows.map((d, i) => (
                      <tr key={i} className="border-t border-edge hover:bg-slate-50">
                        <td className="py-2 pr-3 font-medium text-slate-600">{d.period_end}</td>
                        {hasSubs && <td className={num}>{d.subscriber_count?.toLocaleString() ?? "—"}</td>}
                        {hasSubs && (
                          <td className={`${num} ${(d.subscriber_delta ?? 0) > 0 ? "text-green-600" : (d.subscriber_delta ?? 0) < 0 ? "text-red-600" : "text-slate-400"}`}>
                            {d.subscriber_delta != null ? (d.subscriber_delta > 0 ? `+${d.subscriber_delta}` : d.subscriber_delta) : "—"}
                          </td>
                        )}
                        <td className={num}>{d.avg_views != null ? Math.round(d.avg_views).toLocaleString() : "—"}</td>
                        <td className={num}>{d.avg_er != null ? `${d.avg_er.toFixed(2)}%` : "—"}</td>
                        <td className={num}>{d.total_posts ?? "—"}</td>
                        {hasChurn && <td className={num}>{d.churn_signal ? "!" : "—"}</td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!hasSubs && (
                <p className="mt-3 text-xs text-slate-400">
                  Subscriber counts and churn build up from live samples — Telegram does not expose historical subscriber numbers,
                  so per-day deltas are not available for backfilled history. See the live growth chart above.
                </p>
              )}
            </>
          );
        })()}
      </Card>
    </div>
  );
}
