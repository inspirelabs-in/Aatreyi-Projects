"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { QueueItem } from "@/lib/types";
import { Badge, Card, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";

function fmtSchedule(iso: string | null): string {
  if (!iso) return "Not scheduled";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export default function QueuePage() {
  const { id } = useParams<{ id: string }>();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  async function load() {
    try { setItems(await api.queue(id)); } catch (e) { setError(String(e)); }
  }
  useEffect(() => { load(); }, [id]);

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(); } catch (e) { setError(String(e)); }
  }

  if (error) return <ErrorBox error={error} />;
  if (!items) return <Spinner />;
  if (items.length === 0) return <p className="text-slate-500">Queue is empty — no posts awaiting review.</p>;

  return (
    <div className="space-y-3">
      <p className="text-xs text-slate-500">
        Approve sends to Telegram when BOT_TOKEN is set and the bot is a channel admin.
        Enable auto-approve on the Sources tab to skip manual review.
      </p>
      {items.map((it) => (
        <Card key={it.generated_post_id}>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <Badge tone="blue">{it.post_format}</Badge>
            <span className="inline-flex items-center rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              🗓 {fmtSchedule(it.scheduled_at)}
              <InfoTooltip text="When this post is scheduled to publish. Deal/coupon posts are generated at most 2 days ahead so the offer is still live when it goes out." />
            </span>
            {it.hashtags?.map((h) => <span key={h} className="text-xs text-slate-500">{h}</span>)}
          </div>

          {editing === it.generated_post_id ? (
            <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4}
              className="w-full rounded-lg border border-edge bg-field p-3 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
          ) : (
            <p className="whitespace-pre-wrap text-slate-800">{it.post_text}</p>
          )}

          {it.poll_options && (
            <ul className="mt-2 space-y-1">
              {it.poll_options.map((o, i) => <li key={i} className="text-sm text-slate-500">◻︎ {o}</li>)}
            </ul>
          )}
          {it.cta && (
            it.link_url
              ? <a href={it.link_url} target="_blank" rel="noopener noreferrer"
                   className="mt-2 inline-block rounded-md bg-brand px-3 py-1 text-sm font-medium text-white hover:opacity-90">{it.cta} ↗</a>
              : <p className="mt-2 text-sm text-brand">{it.cta}</p>
          )}
          {it.media_url && <p className="mt-1 truncate text-xs text-slate-500">🖼 {it.media_url}</p>}

          <div className="mt-3 flex gap-2">
            {editing === it.generated_post_id ? (
              <>
                <button onClick={() => act(async () => { await api.edit(id, it.generated_post_id, draft); setEditing(null); })}
                  className="rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-blue-700">Save</button>
                <button onClick={() => setEditing(null)} className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50">Cancel</button>
              </>
            ) : (
              <>
                <button onClick={() => act(() => api.approve(id, it.generated_post_id))}
                  className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-green-700">✅ Approve</button>
                <button onClick={() => { setEditing(it.generated_post_id); setDraft(it.post_text || ""); }}
                  className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:border-brand hover:text-brand">✏️ Edit</button>
                <button onClick={() => act(() => api.reject(id, it.generated_post_id))}
                  className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm transition hover:bg-red-700">❌ Reject</button>
              </>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
