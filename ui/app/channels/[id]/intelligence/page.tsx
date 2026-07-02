"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Intelligence } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Section, Spinner, Stat, Tabs } from "@/components/ui";
import { BarBreakdown, Donut } from "@/components/charts";

export default function IntelligencePage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Intelligence | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("audience");

  useEffect(() => { api.intelligence(id).then(setData).catch((e) => setError(String(e))); }, [id]);

  const intel = data?.intelligence;
  const purpose = useMemo(
    () => (intel?.purpose_mix ? Object.entries(intel.purpose_mix).map(([name, value]) => ({ name, value })) : []),
    [intel],
  );
  const formats = (intel?.format_engagement || []).map((f) => ({ label: f.label, er: f.avg_er }));
  const topics = (intel?.topic_engagement || []).map((t) => ({ label: t.label, er: t.avg_er }));
  const cs = intel?.community_signal;

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;

  return (
    <div>
      <PageHeader title="Intelligence" subtitle="Audience behaviour and retention plan mined by the agents." />
      <Tabs active={tab} onChange={setTab} tabs={[{ key: "audience", label: "Audience" }, { key: "retention", label: "Retention" }]} />

      {tab === "audience" ? (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Posts analysed" value={intel?.posts_analyzed ?? "—"} />
            <Stat label="Viral spikes" value={intel?.spikes ?? "—"} />
            <Stat label="Community" value={cs ? (cs.silent ? "Silent" : cs.state || "Active") : "—"} />
            <Stat label="Reaction density" value={cs?.reaction_density != null ? `${cs.reaction_density}%` : "—"} />
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Section title="Post purpose mix" desc="Why each post exists">
              {purpose.length ? <Donut data={purpose} nameKey="name" valueKey="value" height={220} />
                : <EmptyState title="No purpose data yet" />}
            </Section>
            <Section title="Community signal" desc="How the audience interacts">
              {cs ? (
                <div className="grid grid-cols-2 gap-3">
                  <Stat label="Reaction density" value={`${cs.reaction_density}%`} />
                  <Stat label="Forward rate" value={`${cs.forward_rate}%`} />
                  <Stat label="Poll participation" value={cs.poll_participation != null ? `${cs.poll_participation}%` : "—"} />
                  <Stat label="State" value={cs.silent ? "Silent" : (cs.state || "Active")} />
                </div>
              ) : <EmptyState title="No community signal yet" />}
            </Section>
            <Section title="Engagement by format" desc="Avg ER per format">
              {formats.length ? <BarBreakdown data={formats} x="label" y="er" height={220} /> : <EmptyState title="No format data" />}
            </Section>
            <Section title="Engagement by topic" desc="Avg ER per topic">
              {topics.length ? <BarBreakdown data={topics} x="label" y="er" height={220} /> : <EmptyState title="No topic data" />}
            </Section>
          </div>
        </div>
      ) : (
        <Section title="Retention plan" desc="Habit-loop triggers the Strategy agent scheduled">
          {data.retention_plan?.length ? (
            <ol className="relative max-h-[28rem] space-y-3 overflow-y-auto border-l border-edge pl-5 pr-2">
              {data.retention_plan.map((r, i) => (
                <li key={i} className="relative">
                  <span className="absolute -left-[22px] top-1.5 h-2.5 w-2.5 rounded-full bg-brand" />
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone="blue">{r.kind}</Badge>
                    {r.format && <Badge>{r.format}</Badge>}
                    <span className="text-sm font-medium text-slate-800">{r.topic}</span>
                    {r.date && <span className="text-xs text-slate-400">{r.date}</span>}
                    {r.status && <Badge tone="amber">{r.status}</Badge>}
                  </div>
                </li>
              ))}
            </ol>
          ) : <EmptyState title="No retention plan yet" hint="It appears when engagement dips or churn is detected." />}
        </Section>
      )}
    </div>
  );
}
