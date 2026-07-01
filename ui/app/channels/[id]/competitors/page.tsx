"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Competitor } from "@/lib/types";
import { Badge, EmptyState, ErrorBox, PageHeader, Section, Spinner } from "@/components/ui";

const num = (n: number | null | undefined) => (n == null ? "—" : n.toLocaleString());
const pct = (n: number | null | undefined) => (n == null ? "—" : `${n}%`);

export default function CompetitorsPage() {
  const { id } = useParams<{ id: string }>();
  const [rows, setRows] = useState<Competitor[] | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [handle, setHandle] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try { setRows(await api.competitors(id)); } catch (e) { setError(String(e)); }
  }
  useEffect(() => { load(); }, [id]);

  async function saveHandle(key: string) {
    if (!handle.trim()) return;
    setBusy(true);
    try {
      await api.updateCompetitorHandle(id, key, handle.trim());
      setEditing(null); setHandle("");
      await load();
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  if (error) return <ErrorBox error={error} />;
  if (!rows) return <Spinner />;

  // "Extracted" = its Telegram channel resolved (has subscriber data). Others are
  // known brands whose handle wasn't found yet — those get an Edit action.
  const extracted = rows.filter((c) => c.subscriber_count != null)
    .sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99));
  const pending = rows.filter((c) => c.subscriber_count == null);

  return (
    <div>
      <PageHeader title="Competitors"
        subtitle="Rival channels the Competitor agent found. Extracted channels show live data; add a handle for the rest." />

      <Section title={`On Telegram (${extracted.length})`} desc="Resolved channels with live benchmarks">
        {extracted.length === 0 ? <EmptyState title="No competitor channels resolved yet" hint="Run the Competitor agent." /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr><th className="py-2 pr-3">#</th><th className="pr-3">Competitor</th><th className="pr-3">Subscribers</th><th className="pr-3">ER</th><th className="pr-3">Posts/day</th><th>Themes</th></tr>
              </thead>
              <tbody>
                {extracted.map((c, i) => (
                  <tr key={c.competitor_username} className="border-t border-edge align-top">
                    <td className="py-2 pr-3 text-slate-400">{c.rank ?? i + 1}</td>
                    <td className="py-2 pr-3">
                      <div className="font-medium text-slate-900">{c.display_name || c.competitor_username}</div>
                      <a href={`https://t.me/${c.competitor_username}`} target="_blank" rel="noopener noreferrer"
                         className="text-xs text-brand hover:underline">@{c.competitor_username}</a>
                    </td>
                    <td className="pr-3 text-slate-700">{num(c.subscriber_count)}</td>
                    <td className="pr-3 text-slate-700">{pct(c.avg_er)}</td>
                    <td className="pr-3 text-slate-700">{c.post_frequency_per_day ?? "—"}</td>
                    <td className="text-xs text-slate-500">
                      <div className="flex flex-wrap gap-1">
                        {(c.top_content_themes || []).slice(0, 4).map((t) => <Badge key={t}>{t}</Badge>)}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {pending.length > 0 && (
        <div className="mt-4">
          <Section title={`Also in the market (${pending.length})`} desc="Known brands — add a Telegram handle to track them (re-runs the analysis)">
            <ul className="divide-y divide-edge">
              {pending.map((c) => (
                <li key={c.competitor_username} className="flex flex-wrap items-center gap-3 py-3">
                  <span className="font-medium text-slate-800">{c.display_name || c.competitor_username}</span>
                  <Badge tone="amber">handle not found</Badge>
                  <div className="ml-auto">
                    {editing === c.competitor_username ? (
                      <div className="flex items-center gap-2">
                        <input value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="@handle" autoFocus
                          className="w-40 rounded-lg border border-edge bg-field px-3 py-1.5 text-sm outline-none focus:border-brand" />
                        <button disabled={busy} onClick={() => saveHandle(c.competitor_username)}
                          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">Save</button>
                        <button onClick={() => { setEditing(null); setHandle(""); }}
                          className="rounded-md border border-edge px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50">Cancel</button>
                      </div>
                    ) : (
                      <button onClick={() => { setEditing(c.competitor_username); setHandle(""); }}
                        className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:border-brand hover:text-brand">✏️ Edit / Add handle</button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      )}
    </div>
  );
}
