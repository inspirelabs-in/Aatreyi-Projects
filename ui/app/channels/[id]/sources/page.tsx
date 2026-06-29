"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { ChannelSettings, ContentSourceRow } from "@/lib/types";
import { Badge, Card, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";
import { SECTION_INFO } from "@/lib/descriptions";

export default function SourcesPage() {
  const { id } = useParams<{ id: string }>();
  const [sources, setSources] = useState<ContentSourceRow[] | null>(null);
  const [settings, setSettings] = useState<ChannelSettings | null>(null);
  const [error, setError] = useState("");
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [srcType, setSrcType] = useState<"rss" | "website">("rss");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, st] = await Promise.all([api.listSources(id), api.getSettings(id)]);
      setSources(s);
      setSettings(st);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label);
    try {
      await fn();
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  }

  if (error && !sources) return <ErrorBox error={error} />;
  if (!sources || !settings) return <Spinner label="Loading sources…" />;

  return (
    <div className="space-y-4">
      <Card>
        <h2 className="mb-2 text-sm font-semibold text-slate-800">Publishing settings</h2>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={settings.auto_approve}
            disabled={!!busy}
            onChange={(e) => act("settings", () => api.updateSettings(id, { auto_approve: e.target.checked }))}
          />
          Auto-approve &amp; publish (requires BOT_TOKEN and bot as channel admin)
          <InfoTooltip text={SECTION_INFO.autoApprove} />
        </label>
        <p className="mt-1 text-xs text-slate-500">
          When off, posts go to the Content Factory queue for manual review.
        </p>
      </Card>

      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="flex items-center text-xs text-slate-500">
            Type
            <InfoTooltip text={srcType === "rss" ? SECTION_INFO.rss : SECTION_INFO.website} />
          </label>
          <select value={srcType} onChange={(e) => setSrcType(e.target.value as "rss" | "website")}
            className="block rounded-md border border-edge bg-field px-2 py-1.5 text-sm">
            <option value="rss">RSS feed</option>
            <option value="website">Website</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-slate-500">{srcType === "rss" ? "RSS URL" : "Website URL"}</label>
          <input value={url} onChange={(e) => setUrl(e.target.value)}
            placeholder={srcType === "rss" ? "https://…/feed" : "https://…"}
            className="block w-72 rounded-md border border-edge bg-field px-2 py-1.5 text-sm" />
        </div>
        <div>
          <label className="text-xs text-slate-500">Name</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Source name"
            className="block w-40 rounded-md border border-edge bg-field px-2 py-1.5 text-sm" />
        </div>
        <button disabled={!url || !!busy} onClick={() => act("add", () => api.addSource(id, url, name || undefined, srcType))}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50">
          Add Source
        </button>
        <button disabled={!!busy} onClick={() => act("seed", () => api.seedSources(id))}
          className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700">
          Seed defaults
        </button>
      </div>

      {sources.length === 0 ? (
        <p className="text-sm text-slate-500">No content sources yet — add RSS feeds or seed category defaults.</p>
      ) : (
        <div className="space-y-2">
          {sources.map((s) => (
            <Card key={s.id}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-800">{s.name || s.url}</span>
                <Badge tone={s.is_active ? "green" : "slate"}>{s.is_active ? "active" : "off"}</Badge>
                <Badge>{s.type}</Badge>
                {s.avg_quality_score > 0 && (
                  <span className="inline-flex items-center text-xs text-slate-500">
                    quality {s.avg_quality_score.toFixed(1)}
                    <InfoTooltip text={SECTION_INFO.quality} />
                  </span>
                )}
              </div>
              <p className="mt-1 truncate text-xs text-slate-500">{s.url}</p>
              <div className="mt-2 flex gap-2">
                <button disabled={!!busy}
                  onClick={() => act(`toggle-${s.id}`, () => api.updateSource(id, s.id, { is_active: !s.is_active }))}
                  className="rounded-md border border-edge px-2 py-1 text-xs text-slate-700">
                  {s.is_active ? "Deactivate" : "Activate"}
                </button>
                <button disabled={!!busy}
                  onClick={() => act(`del-${s.id}`, () => api.deleteSource(id, s.id))}
                  className="rounded-md border border-red-200 px-2 py-1 text-xs text-red-600">
                  Delete
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
