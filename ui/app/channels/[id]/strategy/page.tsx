"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Strategy } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, Pagination, PageHeader, Section, Spinner, Stat } from "@/components/ui";
import { Donut } from "@/components/charts";

const PER_PAGE = 8;

export default function StrategyPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Strategy | null>(null);
  const [error, setError] = useState("");
  const [notFound, setNotFound] = useState(false);
  const [page, setPage] = useState(0);

  useEffect(() => {
    api.strategy(id).then(setData).catch((e) => {
      if (String(e).includes("404")) setNotFound(true); else setError(String(e));
    });
  }, [id]);

  const profile = data?.strategy_profile;
  const contentMix = useMemo(() => {
    const cm = data?.content_mix || profile?.content_mix;
    return (cm || []).map((m) => ({ name: m.format, value: m.pct }));
  }, [data, profile]);
  const mediaMix = useMemo(() => (profile?.media_mix || []).map((m) => ({ name: m.media, value: m.pct })), [profile]);

  const tasks = data?.tasks || [];
  const pageCount = Math.max(1, Math.ceil(tasks.length / PER_PAGE));
  const pageTasks = tasks.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE);

  if (error) return <ErrorBox error={error} />;
  if (notFound) return <div><PageHeader title="Strategy" /><EmptyState title="No active strategy yet" hint="Run the Strategy agent to generate the plan." /></div>;
  if (!data) return <Spinner />;

  const b = data.benchmark;
  const timing = profile?.timing;
  const window = timing?.mode === "window" && timing.window
    ? `${timing.window[0]}:00–${(timing.window[1] + 1) % 24 || 24}:00`
    : (timing?.peak_hours || []).map((h) => `${String(h).padStart(2, "0")}:00`).join(", ") || "—";

  return (
    <div>
      <PageHeader title="Strategy" subtitle={data.goal || "The agent's executable plan for this channel."}
        actions={data.strategy_type ? <Badge tone="blue">{data.strategy_type}</Badge> : undefined} />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Posts / day" value={profile?.posts_per_day ?? data.post_frequency_per_day ?? "—"} />
        <Stat label="Your ER" value={b?.my_avg_er != null ? `${b.my_avg_er}%` : "—"} />
        <Stat label="Competitor avg" value={b?.competitor_avg_er != null ? `${b.competitor_avg_er}%` : "—"} />
        <Stat label="Target ER" value={b?.target_er != null ? `${b.target_er}%` : "—"} />
      </div>

      {profile && (
        <div className="mt-6">
          <Section title={`Inferred strategy — ${profile.planner === "dense" ? "dense (high-volume)" : "curated"} profile`}
            desc={profile.rationale}>
            <div className="grid gap-4 lg:grid-cols-3">
              <div className="grid grid-cols-1 gap-3">
                <Stat label="Cadence" value={`${profile.posts_per_day ?? "—"} / day`} />
                <Stat label="Timing" value={window} />
              </div>
              {contentMix.length > 0 && (
                <div><p className="mb-2 text-xs font-medium uppercase text-slate-400">Content mix</p><Donut data={contentMix} nameKey="name" valueKey="value" height={180} /></div>
              )}
              {mediaMix.length > 0 && (
                <div><p className="mb-2 text-xs font-medium uppercase text-slate-400">Media mix</p><Donut data={mediaMix} nameKey="name" valueKey="value" height={180} /></div>
              )}
            </div>
          </Section>
        </div>
      )}

      {(data.primary_topics?.length || 0) > 0 && (
        <div className="mt-4"><Section title="Focus topics">
          <div className="flex flex-wrap gap-2">{data.primary_topics!.map((t) => <Badge key={t} tone="green">{t}</Badge>)}</div>
        </Section></div>
      )}

      {tasks.length > 0 && (
        <div className="mt-4">
          <Section title={`Execution plan — ${tasks.length} slots`}
            desc="Each slot is scraped ~15–20 min before its time, captioned, then queued. Every slot has an evidence-based reason.">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500">
                  <tr><th className="py-2 pr-3">Scrape</th><th className="pr-3">Post</th><th className="pr-3">Type</th><th className="pr-3">Topic</th><th className="pr-3">Market</th><th className="pr-3">Status</th><th>Reason</th></tr>
                </thead>
                <tbody>
                  {pageTasks.map((t) => (
                    <tr key={t.task_id} className="border-t border-edge align-top">
                      <td className="py-2 pr-3 whitespace-nowrap text-xs text-slate-500">{t.scrape_at?.slice(0, 5) || "—"}</td>
                      <td className="pr-3 whitespace-nowrap font-medium text-slate-800">{t.time?.slice(0, 5)}</td>
                      <td className="pr-3"><Badge tone={t.kind === "loot" ? "amber" : "blue"}>{t.kind || t.format}</Badge></td>
                      <td className="pr-3 text-slate-700">{t.topic}</td>
                      <td className="pr-3 text-slate-700">{t.marketplace || "—"}</td>
                      <td className="pr-3"><Badge tone="amber">{t.status}</Badge></td>
                      <td className="whitespace-pre-line text-xs text-slate-500 min-w-[20rem]">{t.rationale}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3"><Pagination page={page} pageCount={pageCount} onPage={setPage} /></div>
          </Section>
        </div>
      )}

      {data.competitor_intelligence && (
        <div className="mt-4"><Section title="Competitor intelligence" desc="Facts guiding the plan (never copied)">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">Opportunities</p>
              <ul className="space-y-1 text-sm text-slate-600">{(data.competitor_intelligence.opportunities || []).slice(0, 5).map((o, i) => <li key={i}>• {o}</li>)}</ul>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">Content gaps</p>
              <div className="flex flex-wrap gap-1">{(data.competitor_intelligence.content_gaps || []).slice(0, 8).map((g) => <Badge key={g}>{g}</Badge>)}</div>
            </div>
            <div>
              <p className="mb-1 text-xs font-medium uppercase text-slate-400">Emerging trends</p>
              <div className="flex flex-wrap gap-1">{(data.competitor_intelligence.emerging_trends || []).slice(0, 8).map((g) => <Badge key={g} tone="green">{g}</Badge>)}</div>
            </div>
          </div>
        </Section></div>
      )}

      {(data.growth_tactics?.length || 0) > 0 && (
        <div className="mt-4"><Section title="Why this plan — diagnosis & actions">
          <ul className="space-y-3">
            {data.growth_tactics!.map((g, i) => (
              <li key={i} className="rounded-lg border border-edge bg-field/40 p-3">
                <div className="flex items-center gap-2">
                  <Badge tone={g.severity === "high" ? "red" : g.severity === "medium" ? "amber" : "slate"}>{g.tactic.replace(/_/g, " ")}</Badge>
                </div>
                {g.why && <p className="mt-2 text-sm text-slate-600"><span className="font-medium text-slate-500">Why: </span>{g.why}</p>}
                {g.action && <p className="mt-1 text-sm text-slate-600"><span className="font-medium text-slate-500">Action: </span>{g.action}</p>}
              </li>
            ))}
          </ul>
        </Section></div>
      )}
    </div>
  );
}
