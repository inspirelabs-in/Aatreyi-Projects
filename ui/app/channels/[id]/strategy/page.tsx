"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { Badge, Collapsible, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";

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
      <Collapsible title="Strategy overview">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="font-medium text-slate-900">{data.goal}</div>
            <div className="flex items-center gap-1 text-xs text-slate-500">
              {data.period_start} → {data.period_end}
              <span className="mx-1">·</span>
              <span className="inline-flex items-center">
                {data.post_frequency_per_day} posts/day
                <InfoTooltip text="Recommended daily posting cadence based on your audience engagement patterns and competitor benchmarks." />
              </span>
            </div>
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
            <span className="inline-flex items-center">
              <Badge tone="slate">your ER {data.benchmark.my_avg_er ?? "—"}%</Badge>
              <InfoTooltip text="Your channel's average engagement rate over the last analytics snapshot period." />
            </span>
            <span className="inline-flex items-center">
              <Badge tone="amber">competitor avg {data.benchmark.competitor_avg_er}%</Badge>
              <InfoTooltip text="Average ER across all confirmed Telegram competitors — used to calibrate your target." />
            </span>
            <span className="inline-flex items-center">
              <Badge tone="green">target {data.benchmark.target_er ?? "—"}%</Badge>
              <InfoTooltip text="The ER target the strategy agent set for the next period based on the gap to top competitors." />
            </span>
          </div>
        )}
      </Collapsible>

      <div className="grid gap-4 md:grid-cols-2">
        <Collapsible title="Content mix">
          <div className="space-y-2">
            {(data.content_mix || []).map((m) => (
              <div key={m.format}>
                <div className="flex justify-between text-sm text-slate-700"><span className="capitalize">{m.format}</span><span className="font-medium text-slate-900">{m.pct}%</span></div>
                <div className="mt-1 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-brand" style={{ width: `${m.pct}%` }} /></div>
              </div>
            ))}
          </div>
        </Collapsible>

        <Collapsible title="Focus topics">
          <div className="flex flex-wrap gap-2">
            {(data.primary_topics || []).map((t) => <Badge key={t} tone="green">{t}</Badge>)}
          </div>
        </Collapsible>
      </div>

      <Collapsible title="🧠 Why this plan — diagnosis &amp; actions">
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
      </Collapsible>

      {((data.growth_recommendations || []).length > 0 || (data.retention_recommendations || []).length > 0) && (
        <Collapsible title="📈 Recommendation engine — growth &amp; retention">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Badge tone="green">Growth</Badge> Grow subscribers &amp; reach
              </div>
              <ul className="space-y-2">
                {(data.growth_recommendations || []).map((r, i) => (
                  <li key={i} className="rounded-lg border border-edge bg-white p-3">
                    <p className="text-sm font-medium text-slate-800">{r.recommendation}</p>
                    {r.why && <p className="mt-1 text-xs text-slate-500">{r.why}</p>}
                  </li>
                ))}
                {(data.growth_recommendations || []).length === 0 && (
                  <li className="text-sm text-slate-400">No growth recommendations yet.</li>
                )}
              </ul>
            </div>
            <div>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800">
                <Badge tone="blue">Retention</Badge> Keep members engaged
              </div>
              <ul className="space-y-2">
                {(data.retention_recommendations || []).map((r, i) => (
                  <li key={i} className="rounded-lg border border-edge bg-white p-3">
                    <p className="text-sm font-medium text-slate-800">{r.recommendation}</p>
                    {r.why && <p className="mt-1 text-xs text-slate-500">{r.why}</p>}
                  </li>
                ))}
                {(data.retention_recommendations || []).length === 0 && (
                  <li className="text-sm text-slate-400">No retention recommendations yet.</li>
                )}
              </ul>
            </div>
          </div>
        </Collapsible>
      )}

      {data.competitor_intelligence && (
        ((data.competitor_intelligence.opportunities || []).length > 0 ||
         (data.competitor_intelligence.content_gaps || []).length > 0 ||
         (data.competitor_intelligence.emerging_trends || []).length > 0) && (
        <Collapsible title="🔍 Competitor intelligence (facts)">
          {(data.competitor_intelligence.opportunities || []).length > 0 && (
            <ul className="space-y-1.5">
              {(data.competitor_intelligence.opportunities || []).map((o, i) => (
                <li key={i} className="rounded-lg bg-slate-50 p-2.5 text-sm text-slate-700">{o}</li>
              ))}
            </ul>
          )}
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {(data.competitor_intelligence.content_gaps || []).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Content gaps</div>
                <div className="flex flex-wrap gap-1">
                  {(data.competitor_intelligence.content_gaps || []).map((t) => (
                    <Badge key={t} tone="amber">{t}</Badge>
                  ))}
                </div>
              </div>
            )}
            {(data.competitor_intelligence.emerging_trends || []).length > 0 && (
              <div>
                <div className="mb-1 text-xs font-semibold uppercase text-slate-500">Emerging trends</div>
                <div className="flex flex-wrap gap-1">
                  {(data.competitor_intelligence.emerging_trends || []).map((t) => (
                    <Badge key={t} tone="blue">{t}</Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        </Collapsible>
        )
      )}

      {(data.competitor_insights || []).length > 0 && (
        <Collapsible title="Competitor insights (similarity-ranked)">
          <div className="space-y-3">
            {(data.competitor_insights || []).map((c, i) => (
              <div key={i} className="rounded-lg border border-edge bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-800">@{c.username}</span>
                  {c.competitor_type && (
                    <Badge tone={c.competitor_type === "direct" ? "red" : c.competitor_type === "aspirational" ? "amber" : "slate"}>{c.competitor_type}</Badge>
                  )}
                  <Badge tone="blue">{Math.round(c.topic_similarity * 100)}% topic overlap</Badge>
                  {c.avg_er != null && (
                    <span className="inline-flex items-center gap-1">
                      <Badge tone="green">{c.avg_er.toFixed(2)}% ER</Badge>
                      <InfoTooltip text="This competitor's engagement rate — used to calibrate your target ER for the strategy period." />
                    </span>
                  )}
                  {c.best_format && <Badge tone="slate">best: {c.best_format}</Badge>}
                  {c.best_time && <Badge tone="slate">peaks {c.best_time}</Badge>}
                </div>
                {c.top_themes.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.top_themes.map((t) => (
                      <span key={t} className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{t}</span>
                    ))}
                  </div>
                )}
                {(c.strengths || []).length > 0 && (
                  <p className="mt-2 text-xs text-slate-500"><span className="font-medium">Strengths: </span>{(c.strengths || []).join("; ")}</p>
                )}
                <p className="mt-2 text-sm text-slate-600">{c.recommendation}</p>
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      <Collapsible title={`Post slots (${data.tasks.length})`}>
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
      </Collapsible>
    </div>
  );
}
