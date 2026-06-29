"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Competitor } from "@/lib/types";
import { Badge, Collapsible, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";

export default function CompetitorsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Competitor[] | null>(null);
  const [error, setError] = useState("");
  const [handles, setHandles] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState<string | null>(null);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  useEffect(() => {
    api.competitors(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

  async function saveHandle(competitorKey: string) {
    const raw = handles[competitorKey] ?? "";
    const handle = raw.replace(/^@/, "").trim();
    if (!handle) return;
    setSaving(competitorKey);
    setSaveMsg(null);
    try {
      await api.updateCompetitorHandle(id, competitorKey, handle);
      setSaveMsg("Handle saved — re-running agents...");
      await Promise.all([
        api.runAgent(id, "analytics"),
        api.runAgent(id, "strategy"),
      ]);
      setSaveMsg("Done! Refreshing...");
      const fresh = await api.competitors(id);
      setData(fresh);
      setSaveMsg(null);
    } catch (e) {
      setSaveMsg(`Error: ${e}`);
    } finally {
      setSaving(null);
    }
  }

  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner />;
  if (data.length === 0) return <p className="text-slate-500">No competitors yet. Run the competitor agent.</p>;

  const onTelegram = data.filter((c) => c.subscriber_count != null);
  const marketOnly = data.filter((c) => c.subscriber_count == null);

  const num = "px-3 py-2 text-right tabular-nums";

  function fmtFreq(f: number | null | undefined): string {
    if (f == null) return "—";
    if (f >= 1) return `${f.toFixed(1)}/day`;
    const perWeek = f * 7;
    if (perWeek >= 1) return `${Math.round(perWeek)}/week`;
    const daysPer = Math.round(1 / f);
    return `1 per ${daysPer}d`;
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-slate-500">
        Competitors are split into channels active on Telegram (with live metrics used for benchmarking)
        and brands present in the market. The strategy agent uses Telegram ER and top posts to calibrate
        your content mix and posting frequency.
      </p>

      {onTelegram.length > 0 && (
        <Collapsible title={`Active on Telegram (${onTelegram.length})`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr className="border-b border-edge">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-4">Competitor</th>
                  <th className="px-3 py-2">Handle</th>
                  <th className={num}>Subscribers</th>
                  <th className={num}>
                    <span className="inline-flex items-center justify-end gap-1">
                      ER %
                      <InfoTooltip text="Engagement rate: (reactions + forwards) ÷ views × 100. Benchmarked daily from their recent posts." />
                    </span>
                  </th>
                  <th className={num}>
                    <span className="inline-flex items-center justify-end gap-1">
                      Posts/day
                      <InfoTooltip text="Average number of posts published per day over the last 30 days." />
                    </span>
                  </th>
                  <th className="px-3 py-2">Top themes</th>
                </tr>
              </thead>
              <tbody className="text-slate-700">
                {onTelegram.map((c) => (
                  <tr key={c.competitor_username} className="border-t border-edge hover:bg-slate-50">
                    <td className="py-2 pr-3 font-semibold text-slate-400">{c.rank ?? "—"}</td>
                    <td className="py-2 pr-4 font-medium text-slate-900">
                      {c.display_name || c.competitor_username}
                      {c.has_disappearing_messages && (
                        <span className="ml-1 text-xs text-amber-500" title="disappearing messages">⏳</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <span className="font-mono text-xs text-brand">@{c.competitor_username}</span>
                    </td>
                    <td className={num}>{c.subscriber_count?.toLocaleString() ?? "—"}</td>
                    <td className={`${num} ${(c.avg_er ?? 0) > 1 ? "text-green-700 font-medium" : ""}`}>
                      {c.avg_er != null ? `${c.avg_er.toFixed(3)}%` : "—"}
                    </td>
                    <td className={num}>{fmtFreq(c.post_frequency_per_day)}</td>
                    <td className="max-w-xs px-3 py-2 text-slate-500 text-xs">
                      {(c.top_content_themes || []).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Ranked by composite score: subscribers 35% · ER 35% · post frequency 15% · topic relevance 15%.
            ER and top posts are refreshed daily.
          </p>
        </Collapsible>
      )}

      {marketOnly.length > 0 && (
        <Collapsible title={`Also in the market (${marketOnly.length})`}>
          <p className="mb-3 text-xs text-slate-500">
            These brands compete in the same space but their Telegram channel wasn&apos;t confirmed.
            If you know their Telegram handle, add it below — the agents will re-run automatically.
          </p>
          {saveMsg && (
            <div className="mb-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-700">
              {saveMsg}
            </div>
          )}
          <div className="space-y-3">
            {marketOnly.map((c) => (
              <div key={c.competitor_username} className="rounded-lg border border-edge bg-white p-3">
                <div className="font-medium text-slate-800">{c.display_name || c.competitor_username}</div>
                <div className="mt-2 flex gap-2">
                  <input
                    type="text"
                    className="flex-1 rounded-lg border border-edge bg-slate-50 px-3 py-1.5 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                    placeholder="@telegram_handle"
                    value={handles[c.competitor_username] ?? ""}
                    onChange={(e) =>
                      setHandles((h) => ({ ...h, [c.competitor_username]: e.target.value }))
                    }
                    disabled={saving === c.competitor_username}
                  />
                  <button
                    type="button"
                    onClick={() => saveHandle(c.competitor_username)}
                    disabled={saving === c.competitor_username || !(handles[c.competitor_username] ?? "").trim()}
                    className="rounded-lg bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand/90 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {saving === c.competitor_username ? "Saving…" : "Add & Re-run"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      {onTelegram.length === 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <strong>No Telegram channels resolved yet.</strong> The agent found {marketOnly.length} market
          competitors but couldn&apos;t confirm their Telegram handles. Add handles above or re-run the competitor agent.
        </div>
      )}
    </div>
  );
}
