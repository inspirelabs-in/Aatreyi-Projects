"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Competitor } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

export default function CompetitorsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<Competitor[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.competitors(id).then(setData).catch((e) => setError(String(e)));
  }, [id]);

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
        <Card title={`Active on Telegram (${onTelegram.length})`}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-slate-500">
                <tr className="border-b border-edge">
                  <th className="py-2 pr-3">#</th>
                  <th className="py-2 pr-4">Competitor</th>
                  <th className="px-3 py-2">Handle</th>
                  <th className={num}>Subscribers</th>
                  <th className={num}>ER %</th>
                  <th className={num}>Posts/day</th>
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
        </Card>
      )}

      {marketOnly.length > 0 && (
        <Card title={`Also in the market (${marketOnly.length})`}>
          <p className="mb-3 text-xs text-slate-500">
            These brands compete in the same space but their Telegram channel wasn't confirmed.
            Re-run the competitor agent to check again — some may have channels the agent couldn't resolve yet.
          </p>
          <div className="flex flex-wrap gap-2">
            {marketOnly.map((c) => (
              <span
                key={c.competitor_username}
                className="rounded-full border border-edge bg-slate-50 px-3 py-1 text-sm text-slate-700"
              >
                {c.display_name || c.competitor_username}
              </span>
            ))}
          </div>
        </Card>
      )}

      {onTelegram.length === 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          <strong>No Telegram channels resolved yet.</strong> The agent found {marketOnly.length} market
          competitors but couldn't confirm their Telegram handles. Re-run the competitor agent — it now
          uses Telegram&apos;s native search (more reliable than web search) to find channel handles.
        </div>
      )}
    </div>
  );
}
