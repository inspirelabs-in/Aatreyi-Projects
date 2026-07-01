"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { QueueItem } from "@/lib/types";
import { Badge, ErrorBox, InfoTooltip, Spinner } from "@/components/ui";

const PER_PAGE = 6;

function fmtSchedule(iso: string | null): string {
  if (!iso) return "Not scheduled";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    weekday: "short", month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

const URL_RE = /(https?:\/\/[^\s]+)/g;

// Render plain text with bare URLs turned into clickable links.
function linkify(text: string): React.ReactNode {
  return text.split(URL_RE).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={i} href={part} target="_blank" rel="noopener noreferrer"
         className="break-all text-brand underline hover:opacity-80">{part}</a>
    ) : (
      <React.Fragment key={i}>{part}</React.Fragment>
    )
  );
}

// Our deal/loot posts are Telegram HTML (parse_mode=HTML): <b>…</b> headings and
// <a href>…</a> item links. Render that safely — allow only Telegram's tag subset,
// force links to open externally, and drop anything else — so the card shows the
// post exactly as it will appear on Telegram (bold + tappable), never raw tags.
const ALLOWED: Record<string, string[]> = {
  B: [], STRONG: [], I: [], EM: [], U: [], S: [], DEL: [], CODE: [], PRE: [], BR: [], A: ["href"],
};
function sanitizeTelegramHtml(html: string): string {
  if (typeof window === "undefined") return "";
  const doc = new DOMParser().parseFromString(html, "text/html");
  const walk = (node: Node) => {
    Array.from(node.childNodes).forEach((child) => {
      if (child.nodeType !== 1) return;
      const el = child as HTMLElement;
      const tag = el.tagName;
      if (!(tag in ALLOWED)) {
        el.replaceWith(document.createTextNode(el.textContent || ""));
        return;
      }
      Array.from(el.attributes).forEach((a) => {
        if (!ALLOWED[tag].includes(a.name)) el.removeAttribute(a.name);
      });
      if (tag === "A") {
        const href = el.getAttribute("href") || "";
        if (!/^https?:\/\//i.test(href)) el.removeAttribute("href");
        else { el.setAttribute("target", "_blank"); el.setAttribute("rel", "noopener noreferrer"); }
      }
      walk(el);
    });
  };
  walk(doc.body);
  return doc.body.innerHTML;
}

function PostBody({ text }: { text: string | null }) {
  const isHtml = !!text && /<(b|strong|i|em|a|u|s|code|pre)\b/i.test(text);
  const html = useMemo(() => (isHtml ? sanitizeTelegramHtml(text!) : ""), [text, isHtml]);
  if (!text) return null;
  if (isHtml) {
    return (
      <div
        className="tg-post whitespace-pre-wrap break-words text-[15px] leading-relaxed text-slate-800 [&_a]:text-brand [&_a]:underline [&_a]:break-all [&_b]:font-semibold [&_strong]:font-semibold"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  }
  return <p className="whitespace-pre-wrap break-words text-[15px] leading-relaxed text-slate-800">{linkify(text)}</p>;
}

export default function QueuePage() {
  const { id } = useParams<{ id: string }>();
  const [items, setItems] = useState<QueueItem[] | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [page, setPage] = useState(0);

  async function load() {
    try { setItems(await api.queue(id)); } catch (e) { setError(String(e)); }
  }
  useEffect(() => { load(); }, [id]);

  async function act(fn: () => Promise<unknown>) {
    try { await fn(); await load(); } catch (e) { setError(String(e)); }
  }

  const pageCount = items ? Math.max(1, Math.ceil(items.length / PER_PAGE)) : 1;
  const pageItems = useMemo(
    () => (items ? items.slice(page * PER_PAGE, page * PER_PAGE + PER_PAGE) : []),
    [items, page],
  );
  useEffect(() => { if (page >= pageCount) setPage(0); }, [pageCount, page]);

  if (error) return <ErrorBox error={error} />;
  if (!items) return <Spinner />;
  if (items.length === 0) return <p className="text-slate-500">Queue is empty — no posts awaiting review.</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-500">
          {items.length} post{items.length === 1 ? "" : "s"} awaiting review · previewed exactly as they'll appear on Telegram.
        </p>
        <span className="text-xs text-slate-400">Page {page + 1} / {pageCount}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {pageItems.map((it) => {
          const url = it.link_url || null;
          const cta = it.cta ? it.cta.replace(URL_RE, "").replace(/[:\-–\s]+$/, "").trim() : "";
          return (
            <div key={it.generated_post_id}
              className="flex flex-col overflow-hidden rounded-2xl border border-edge bg-panel shadow-card">
              {/* Telegram-style header */}
              <div className="flex items-center gap-2 border-b border-edge bg-slate-50/70 px-4 py-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-xs font-bold text-white">TG</span>
                <span className="text-sm font-medium text-slate-700">Channel preview</span>
                <Badge tone="blue">{it.post_format}</Badge>
                <span className="ml-auto inline-flex items-center rounded-md bg-white px-2 py-0.5 text-xs font-medium text-slate-500 ring-1 ring-inset ring-slate-200">
                  🗓 {fmtSchedule(it.scheduled_at)}
                  <InfoTooltip text="When this post publishes. Deal posts are generated ~15–20 min before their slot so the offer is still live." />
                </span>
              </div>

              {/* Telegram-style message bubble */}
              <div className="flex-1 px-4 py-3">
                {it.media_url && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={it.media_url} alt="" className="mb-3 max-h-56 w-full rounded-lg object-cover"
                       onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }} />
                )}
                {editing === it.generated_post_id ? (
                  <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={6}
                    className="w-full rounded-lg border border-edge bg-field p-3 text-sm text-slate-800 outline-none transition focus:border-brand focus:ring-2 focus:ring-brand/20" />
                ) : (
                  <PostBody text={it.post_text} />
                )}
                {it.poll_options && (
                  <ul className="mt-2 space-y-1">
                    {it.poll_options.map((o, i) => <li key={i} className="text-sm text-slate-500">◻︎ {o}</li>)}
                  </ul>
                )}
                {url && cta && (
                  <a href={url} target="_blank" rel="noopener noreferrer"
                     className="mt-3 inline-flex w-full items-center justify-center rounded-lg bg-blue-50 px-3 py-2 text-sm font-semibold text-brand ring-1 ring-inset ring-blue-200 hover:bg-blue-100">
                    {cta} ↗
                  </a>
                )}
              </div>

              {/* Actions */}
              <div className="flex gap-2 border-t border-edge px-4 py-3">
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
            </div>
          );
        })}
      </div>

      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-2 pt-2">
          <button disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}
            className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-40">← Prev</button>
          {Array.from({ length: pageCount }).map((_, i) => (
            <button key={i} onClick={() => setPage(i)}
              className={`h-8 w-8 rounded-md text-sm transition ${i === page ? "bg-brand font-medium text-white" : "border border-edge bg-panel text-slate-600 hover:bg-slate-50"}`}>{i + 1}</button>
          ))}
          <button disabled={page >= pageCount - 1} onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
            className="rounded-md border border-edge bg-panel px-3 py-1.5 text-sm text-slate-700 transition hover:bg-slate-50 disabled:opacity-40">Next →</button>
        </div>
      )}
    </div>
  );
}
