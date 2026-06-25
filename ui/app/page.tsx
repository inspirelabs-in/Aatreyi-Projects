"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChannelSummary } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

export default function Home() {
  const router = useRouter();
  const [channels, setChannels] = useState<ChannelSummary[] | null>(null);
  const [error, setError] = useState("");
  const [username, setUsername] = useState("");
  const [category, setCategory] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setChannels(await api.listChannels());
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => { load(); }, []);

  async function onboard(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim()) return;
    setBusy(true);
    try {
      const res = await api.onboard({ telegram_username: username.trim(), category: category.trim() || undefined });
      setUsername(""); setCategory("");
      // Onboarding pipeline auto-starts in the background — jump to the live
      // Control Room so the user watches the agents run.
      router.push(`/channels/${res.channel_id}`);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Add a channel">
        <form onSubmit={onboard} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-600">Telegram username</label>
            <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="@mychannel"
              className="mt-1 w-64 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600">Category (optional)</label>
            <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="deals, tech…"
              className="mt-1 w-48 rounded-lg border border-edge bg-field px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          </div>
          <button disabled={busy} className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700 disabled:opacity-50">
            {busy ? "Adding…" : "Add channel"}
          </button>
        </form>
        <p className="mt-2 text-xs text-slate-500">Agents start automatically — we detect the channel's subscribers, pick its tier, and run the pipeline. You'll land in its live Control Room.</p>
      </Card>

      {error && <ErrorBox error={error} />}
      {channels === null ? (
        <Spinner />
      ) : channels.length === 0 ? (
        <p className="text-slate-500">No channels yet.</p>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map((c) => (
            <Link key={c.id} href={`/channels/${c.id}`}
              className="rounded-xl border border-edge bg-panel p-4 shadow-card transition hover:border-brand hover:shadow-md">
              <div className="flex items-center justify-between">
                <span className="font-medium text-slate-900">@{c.telegram_username}</span>
                {c.tier && <Badge tone="blue">{c.tier}</Badge>}
              </div>
              <div className="mt-1 truncate text-sm text-slate-500">{c.display_name || "—"}</div>
              <div className="mt-2 flex gap-2 text-xs text-slate-500">
                {c.category && <Badge>{c.category}</Badge>}
                {c.status && <Badge tone="amber">{c.status}</Badge>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
