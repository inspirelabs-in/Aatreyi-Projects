"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/lib/api";
import type { AnalyticsPoint, SubscriberPoint } from "@/lib/types";
import { Badge, Collapsible, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";

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

function useContainerWidth(ref: React.RefObject<HTMLDivElement | null>): number {
  const [width, setWidth] = useState(700);
  useEffect(() => {
    if (!ref.current) return;
    setWidth(ref.current.clientWidth || 700);
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect?.width;
      if (w) setWidth(Math.floor(w));
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, [ref]);
  return width;
}

export default function AnalyticsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<AnalyticsPoint[] | null>(null);
  const [subs, setSubs] = useState<SubscriberPoint[]>([]);
  const [error, setError] = useState("");
  const [mounted, setMounted] = useState(false);

  const subRef = useRef<HTMLDivElement>(null);
  const erRef = useRef<HTMLDivElement>(null);
  const subWidth = useContainerWidth(subRef);
  const erWidth = useContainerWidth(erRef);

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

  const subChart = subs
    .filter((s) => s.subscriber_count != null)
    .map((s) => ({
      t: s.ts ? new Date(s.ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "",
      subscribers: s.subscriber_count,
    }));

  const timeline = buildTimeline(data);
  const hasErData = chart.some((d) => d.er > 0);
  const tooltipStyle = { background: "#ffffff", border: "1px solid #e5e7eb", borderRadius: 8, color: "#0f172a" };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">What the agents discovered</h1>
        <p className="text-sm text-slate-500">Analytics is a byproduct of agent execution — these are the signals the Analytics Agent surfaced and the Strategy Agent acts on.</p>
      </div>

      <Collapsible title="Insight timeline">
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
      </Collapsible>

      <p className="pt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Supporting visuals (agent-derived)</p>

      <Collapsible title="Subscriber growth (live — sampled every ~20 min)">
        <div ref={subRef} className="w-full">
          {!mounted || subChart.length === 0 ? (
            <p className="text-sm text-slate-500">
              Collecting live subscriber samples... the poller records the count every ~20 min.
              Telegram does not expose historical counts, so this chart builds up from now.
            </p>
          ) : (
            <LineChart width={subWidth} height={256} data={subChart} margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="t" stroke="#94a3b8" fontSize={10} interval="preserveStartEnd" tick={{ dy: 6 }} />
              <YAxis
                stroke="#94a3b8" fontSize={11} width={52} tickCount={5} domain={["auto", "auto"]}
                tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v)}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="subscribers" stroke="#2563eb" strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </div>
      </Collapsible>

      <Collapsible title={
        <span className="flex items-center gap-1">
          Engagement rate (%)
          <InfoTooltip text="Average engagement rate per snapshot period: (reactions + forwards) ÷ views × 100. Higher = posts resonating more." />
        </span>
      }>
        <div ref={erRef} className="w-full">
          {!mounted ? (
            <p className="text-sm text-slate-500">Loading...</p>
          ) : !hasErData ? (
            <p className="text-sm text-slate-500">
              No engagement rate data yet — the Analytics agent needs at least one run with real post data.
            </p>
          ) : (
            <LineChart width={erWidth} height={224} data={chart} margin={{ top: 10, right: 20, bottom: 20, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis dataKey="date" stroke="#94a3b8" fontSize={10} interval="preserveStartEnd" tick={{ dy: 6 }} />
              <YAxis
                stroke="#94a3b8" fontSize={11} width={52} tickCount={5} domain={[0, "dataMax + 0.5"]}
                tickFormatter={(v: number) => `${v.toFixed(2)}%`}
              />
              <Tooltip formatter={(v: number) => [`${v.toFixed(3)}%`, "ER"]} contentStyle={tooltipStyle} />
              <Line type="monotone" dataKey="er" stroke="#16a34a" strokeWidth={2} dot={false} />
            </LineChart>
          )}
        </div>
      </Collapsible>

      <Collapsible title="Snapshots">
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
                      {hasSubs && (
                        <th className="px-3 py-2 text-right">
                          <span className="inline-flex items-center justify-end">
                            Delta
                            <InfoTooltip text="Daily subscriber change. Positive = growth, negative = churn. Built from live samples every ~20 min." />
                          </span>
                        </th>
                      )}
                      <th className="px-3 py-2 text-right">Views</th>
                      <th className="px-3 py-2 text-right">
                        <span className="inline-flex items-center justify-end">
                          ER
                          <InfoTooltip text="Engagement rate: (reactions + forwards) ÷ views × 100. Measures how actively the audience responds." />
                        </span>
                      </th>
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
                  Subscriber counts build up from live samples — per-day deltas are not available for backfilled history.
                </p>
              )}
            </>
          );
        })()}
      </Collapsible>
    </div>
  );
}
