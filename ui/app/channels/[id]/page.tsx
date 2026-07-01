"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { AnalyticsPoint, Dashboard, Intelligence, Strategy, SubscriberPoint } from "@/lib/types";
import { EmptyState, ErrorBox, PageHeader, Section, Spinner, Stat } from "@/components/ui";
import { AreaTrend, BarBreakdown, Donut, LineTrend } from "@/components/charts";

function shortTime(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit" });
}
const pct = (n: number | null | undefined) => (n == null ? "—" : `${n}%`);
const num = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());

export default function DashboardPage() {
  const { id } = useParams<{ id: string }>();
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [subs, setSubs] = useState<SubscriberPoint[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsPoint[]>([]);
  const [intel, setIntel] = useState<Intelligence | null>(null);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [d, s, a, i] = await Promise.all([
          api.dashboard(id), api.subscribers(id, 300), api.analytics(id, "daily", 30), api.intelligence(id),
        ]);
        setDash(d); setSubs(s); setAnalytics(a); setIntel(i);
        api.strategy(id).then(setStrategy).catch(() => setStrategy(null));
      } catch (e) { setError(String(e)); }
    })();
  }, [id]);

  const subSeries = useMemo(
    () => subs.filter((p) => p.subscriber_count != null).map((p) => ({ t: shortTime(p.ts), subscribers: p.subscriber_count })),
    [subs],
  );
  const erSeries = useMemo(
    () => [...analytics].reverse().filter((p) => p.avg_er != null)
      .map((p) => ({ date: shortTime(p.period_end).replace(/,.*/, ""), er: p.avg_er })),
    [analytics],
  );
  const formatBars = useMemo(
    () => (intel?.intelligence.format_engagement || []).map((f) => ({ label: f.label, er: f.avg_er })),
    [intel],
  );
  const mixDonut = useMemo(() => {
    const cm = strategy?.content_mix || strategy?.strategy_profile?.content_mix;
    if (cm?.length) return cm.map((m) => ({ name: m.format, value: m.pct }));
    const pm = intel?.intelligence.purpose_mix;
    return pm ? Object.entries(pm).map(([name, value]) => ({ name, value })) : [];
  }, [strategy, intel]);

  if (error) return <ErrorBox error={error} />;
  if (!dash) return <Spinner />;
  const k = dash.kpis;

  return (
    <div>
      <PageHeader title="Dashboard" subtitle="What the Analytics agent is tracking — live growth, engagement and mix." />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Subscribers" value={num(k.subscriber_count)}
          sub={k.subscriber_delta_pct != null ? `${k.subscriber_delta_pct >= 0 ? "+" : ""}${k.subscriber_delta_pct}% period` : undefined} />
        <Stat label="Engagement rate" value={pct(k.avg_er)} />
        <Stat label="Posts / day" value={k.post_frequency_per_day ?? "—"} />
        <Stat label="Pending review" value={k.pending_review} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <Section title="Subscriber growth" desc="Live samples (~20 min)">
          {subSeries.length > 1 ? <AreaTrend data={subSeries} x="t" y="subscribers" height={240} />
            : <EmptyState title="Not enough samples yet" hint="Subscriber polling builds this over time." />}
        </Section>
        <Section title="Engagement rate (%)" desc="Per analytics snapshot">
          {erSeries.length > 1 ? <LineTrend data={erSeries} x="date" y="er" height={240} />
            : <EmptyState title="No engagement history yet" hint="Run the Analytics agent to populate." />}
        </Section>
        <Section title="Engagement by format" desc="Avg ER per content format">
          {formatBars.length ? <BarBreakdown data={formatBars} x="label" y="er" height={240} />
            : <EmptyState title="No format data yet" hint="Comes from the Intelligence agent." />}
        </Section>
        <Section title="Content mix" desc="Planned format / purpose split">
          {mixDonut.length ? <Donut data={mixDonut} nameKey="name" valueKey="value" height={240} />
            : <EmptyState title="No mix yet" hint="Run the Strategy agent." />}
        </Section>
      </div>

      {dash.insights?.length > 0 && (
        <div className="mt-6">
          <Section title="Insights" desc="What the agents flagged">
            <ul className="space-y-2">
              {dash.insights.slice(0, 8).map((it, i) => (
                <li key={i} className="flex gap-2 text-sm text-slate-700">
                  <span className="text-brand">•</span><span><span className="font-medium capitalize">{it.type}: </span>{it.note}</span>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      )}
    </div>
  );
}
