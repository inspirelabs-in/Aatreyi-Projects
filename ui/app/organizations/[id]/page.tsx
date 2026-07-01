"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChannelSummary, Competitor, Organization } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Section, Spinner } from "@/components/ui";

const num = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());

export default function OrgDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [org, setOrg] = useState<Organization | null>(null);
  const [channels, setChannels] = useState<ChannelSummary[]>([]);
  const [competitors, setCompetitors] = useState<Competitor[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [orgs, chs] = await Promise.all([api.organizations(), api.listChannels()]);
        setOrg(orgs.find((o) => o.id === id) || null);
        const mine = chs.filter((c) => c.organization_id === id);
        setChannels(mine);
        // Aggregate competitors across the org's channels (dedupe by handle).
        const seen = new Map<string, Competitor>();
        for (const c of mine.slice(0, 12)) {
          try {
            const list = await api.competitors(c.id);
            for (const comp of list) {
              const key = (comp.competitor_username || comp.display_name || "").toLowerCase();
              if (key && (!seen.has(key) || (comp.subscriber_count != null && seen.get(key)!.subscriber_count == null)))
                seen.set(key, comp);
            }
          } catch { /* skip channel on error */ }
        }
        setCompetitors([...seen.values()].sort((a, b) => (b.subscriber_count ?? -1) - (a.subscriber_count ?? -1)));
      } catch (e) { setError(String(e)); } finally { setLoading(false); }
    })();
  }, [id]);

  if (error) return <ErrorBox error={error} />;
  if (loading) return <Spinner />;

  return (
    <div>
      <PageHeader title={org ? org.name : "Organization"} subtitle={org ? `@${org.slug} · ${channels.length} channel${channels.length === 1 ? "" : "s"}` : undefined} />

      <Section title="Channels" desc="Telegram channels in this organization">
        {channels.length === 0 ? <EmptyState title="No channels in this organization yet" /> : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {channels.map((c) => (
              <Link key={c.id} href={`/channels/${c.id}`}
                className="rounded-xl border border-edge bg-field/40 p-4 transition hover:border-brand hover:bg-white">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-900">@{c.telegram_username}</span>
                  {c.tier && <Badge tone="blue">{c.tier}</Badge>}
                </div>
                <div className="mt-2 flex flex-wrap gap-2 text-xs">
                  {c.category && <Badge>{c.category}</Badge>}
                  {c.status && <Badge tone="amber">{c.status}</Badge>}
                </div>
              </Link>
            ))}
          </div>
        )}
      </Section>

      <div className="mt-4">
        <Section title={`Competitors (${competitors.length})`} desc="Aggregated across this organization's channels">
          {competitors.length === 0 ? <EmptyState title="No competitors tracked yet" hint="Run the Competitor agent on a channel." /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs uppercase text-slate-500">
                  <tr><th className="py-2 pr-3">Competitor</th><th className="pr-3">Handle</th><th className="pr-3">Subscribers</th><th>ER</th></tr>
                </thead>
                <tbody>
                  {competitors.map((c) => (
                    <tr key={c.competitor_username} className="border-t border-edge">
                      <td className="py-2 pr-3 font-medium text-slate-800">{c.display_name || c.competitor_username}</td>
                      <td className="pr-3">
                        {c.subscriber_count != null
                          ? <a href={`https://t.me/${c.competitor_username}`} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">@{c.competitor_username}</a>
                          : <Badge tone="amber">pending</Badge>}
                      </td>
                      <td className="pr-3 text-slate-700">{num(c.subscriber_count)}</td>
                      <td className="text-slate-700">{c.avg_er != null ? `${c.avg_er}%` : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
    </div>
  );
}
