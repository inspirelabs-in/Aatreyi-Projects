"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChannelSummary, Me, Organization } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Section, Spinner } from "@/components/ui";

export default function ChannelsPage() {
  const router = useRouter();
  const [channels, setChannels] = useState<ChannelSummary[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [category, setCategory] = useState("");
  const [orgId, setOrgId] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const [chs, m] = await Promise.all([api.listChannels(), api.me()]);
      setChannels(chs); setMe(m);
      if (m.is_platform_admin) {
        const all = await api.organizations();
        setOrgs(all); setOrgId(m.organization_id || (all[0]?.id ?? ""));
      }
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { load(); }, []);

  const orgName = (id?: string) => orgs.find((o) => o.id === id)?.slug;

  async function onboard(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setBusy(true);
    try {
      const res = await api.onboard({
        telegram_username: username.trim(),
        category: category.trim() || undefined,
        organization_id: me?.is_platform_admin ? orgId || undefined : undefined,
      });
      setUsername(""); setCategory("");
      router.push(`/channels/${res.channel_id}`);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  return (
    <div>
      <PageHeader title="Channels" subtitle="Your Telegram channels — each runs the full agent pipeline." />

      <Section title="Add a channel">
        <form onSubmit={onboard} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600">Telegram username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="@mychannel"
              className="mt-1 w-64 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Category (optional)</label>
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="deals, tech…"
              className="mt-1 w-48 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          {me?.is_platform_admin && orgs.length > 0 && (
            <div>
              <label className="block text-xs font-medium text-slate-600">Organization</label>
              <select value={orgId} onChange={(e) => setOrgId(e.target.value)}
                className="mt-1 w-52 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-brand">
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name} ({o.slug})</option>)}
              </select>
            </div>
          )}
          <button disabled={busy}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50">
            {busy ? "Adding…" : "Add channel"}
          </button>
        </form>
        <p className="mt-2 text-xs text-slate-500">Agents start automatically — we detect subscribers, pick the tier, and run the pipeline.</p>
      </Section>

      <div className="mt-6">
        {error && <ErrorBox error={error} />}
        {channels === null ? <Spinner /> : channels.length === 0 ? (
          <EmptyState title="No channels yet" hint="Add your first channel above to get started." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {channels.map((c) => (
              <Link key={c.id} href={`/channels/${c.id}`}
                className="rounded-2xl border border-edge bg-panel p-4 shadow-card transition hover:border-brand hover:shadow-md">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-900">@{c.telegram_username}</span>
                  {c.tier && <Badge tone="blue">{c.tier}</Badge>}
                </div>
                <div className="mt-1 truncate text-sm text-slate-500">{c.display_name || "—"}</div>
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {c.category && <Badge>{c.category}</Badge>}
                  {c.status && <Badge tone="amber">{c.status}</Badge>}
                  {me?.is_platform_admin && orgName(c.organization_id) && <Badge tone="green">{orgName(c.organization_id)}</Badge>}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
