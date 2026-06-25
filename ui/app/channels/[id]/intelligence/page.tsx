"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Intelligence } from "@/lib/types";
import { Badge, Card, Collapsible, ErrorBox, InfoTooltip, Spinner, Stat } from "@/components/ui";

const PURPOSE_TONE: Record<string, "green" | "blue" | "amber" | "slate"> = {
  growth: "green", retention: "blue", conversion: "amber", standard: "slate",
};

export default function IntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Intelligence | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.intelligence(id).then(setData).catch((e) => setError(String(e))); }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;

  const it = data.intelligence || {};
  const cs = it.community_signal;
  const noData = !it.posts_analyzed;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">📡 Audience & Content Intelligence</h1>
        <p className="text-sm text-slate-500">What the Analytics Agent learned from post signals — virality, stickiness, and the retention plan acting on it.</p>
      </div>

      {noData ? (
        <Card><p className="text-sm text-slate-500">No post intelligence yet — run the Analytics agent on a channel with recent posts.</p></Card>
      ) : (
        <>
          <Collapsible title="Post purpose mix (virality layer)">
            <div className="flex flex-wrap gap-2">
              {Object.entries(it.purpose_mix || {}).map(([k, v]) => (
                <Badge key={k} tone={PURPOSE_TONE[k] || "slate"}>{k}: {v}</Badge>
              ))}
              <span className="ml-auto text-xs text-slate-400">{it.posts_analyzed} posts · {it.spikes ?? 0} break-out spike(s)</span>
            </div>
          </Collapsible>

          <div className="grid gap-4 md:grid-cols-2">
            <Collapsible title="Community signal">
              {cs && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className={`h-2.5 w-2.5 rounded-full ${cs.silent ? "bg-red-500" : cs.state === "active" ? "bg-green-500" : "bg-amber-500"}`} />
                    <span className="font-medium capitalize text-slate-800">{cs.silent ? "Silent channel" : cs.state}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Stat
                      label="Reaction density"
                      value={`${cs.reaction_density}%`}
                      info="% of viewers who reacted to posts (reactions ÷ views × 100). Higher = more emotional resonance."
                    />
                    <Stat
                      label="Forward rate"
                      value={`${cs.forward_rate}%`}
                      info="% of viewers who forwarded posts to others. A strong virality signal — content people want to share."
                    />
                  </div>
                  {cs.poll_participation != null && (
                    <div className="flex items-center text-xs text-slate-500">
                      Poll participation: {cs.poll_participation}%
                      <InfoTooltip text="% of viewers who voted in poll posts. Indicates active audience engagement beyond passive reading." />
                    </div>
                  )}
                </div>
              )}
            </Collapsible>

            <Collapsible title="What engages best (format → ER)">
              <ul className="space-y-1 text-sm">
                {(it.format_engagement || []).map((f) => (
                  <li key={f.label} className="flex justify-between">
                    <span className="capitalize text-slate-700">{f.label}</span>
                    <span className="text-slate-500">
                      {f.avg_er}%
                      <InfoTooltip text={`Avg engagement rate for ${f.label} posts — (reactions + forwards) ÷ views × 100`} />
                      · {f.posts} posts
                    </span>
                  </li>
                ))}
                {(it.format_engagement || []).length === 0 && <li className="text-sm text-slate-400">—</li>}
              </ul>
            </Collapsible>
          </div>

          <Collapsible title="♻️ Recycle candidates (content lifecycle)">
            {(it.recycle_candidates || []).length === 0 ? (
              <p className="text-sm text-slate-500">No break-out posts to recycle yet.</p>
            ) : (
              <ul className="space-y-2">
                {(it.recycle_candidates || []).map((r, i) => (
                  <li key={i} className="rounded-lg border border-edge bg-white p-2.5 text-sm">
                    <div className="flex items-center gap-2">
                      <Badge tone="green">{r.er}% ER</Badge>
                      <span className="truncate text-slate-700">{r.text_preview}</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-500">{r.suggestion}</div>
                  </li>
                ))}
              </ul>
            )}
          </Collapsible>
        </>
      )}

      <Collapsible title="🔁 Retention plan — habit-loop triggers scheduled">
        {data.retention_plan.length === 0 ? (
          <p className="text-sm text-slate-500">No retention triggers active — channel is healthy, running the standard plan.</p>
        ) : (
          <ul className="space-y-2">
            {data.retention_plan.map((t, i) => (
              <li key={i} className="flex items-center gap-2 rounded-lg border border-edge bg-white p-2.5 text-sm">
                <Badge tone="blue">{t.kind}</Badge>
                <Badge>{t.format}</Badge>
                <span className="text-slate-700">{t.topic}</span>
                <span className="ml-auto text-xs text-slate-400">{t.date} · {t.status}</span>
              </li>
            ))}
          </ul>
        )}
      </Collapsible>
    </div>
  );
}
