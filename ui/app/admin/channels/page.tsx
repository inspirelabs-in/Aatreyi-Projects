"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AdminChannelRow } from "@/lib/types";
import { Badge, Card, ErrorBox, Spinner } from "@/components/ui";

const DOT: Record<string, string> = { done: "bg-green-500", running: "bg-blue-500", failed: "bg-red-500", idle: "bg-slate-300" };

export default function AllChannels() {
  const [rows, setRows] = useState<AdminChannelRow[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api.adminChannels().then(setRows).catch((e) => setError(String(e))); }, []);

  if (error) return <ErrorBox error={error} />;
  if (!rows) return <Spinner />;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold text-slate-900">All Channels <span className="text-sm font-normal text-slate-500">({rows.length} tenants)</span></h1>
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-500">
              <tr><th className="py-2">Channel</th><th>Tier</th><th>Category</th><th>Subs</th><th>ER</th><th>Last agent</th><th>Pending</th><th></th></tr>
            </thead>
            <tbody className="text-slate-700">
              {rows.map((c) => (
                <tr key={c.id} className="border-t border-edge">
                  <td className="py-2">
                    <div className="font-medium text-slate-900">@{c.telegram_username}</div>
                    <div className="truncate text-xs text-slate-400">{c.display_name || "—"}</div>
                  </td>
                  <td>{c.tier && <Badge tone="blue">{c.tier}</Badge>}</td>
                  <td>{c.category || "—"}</td>
                  <td>{c.subscriber_count?.toLocaleString() ?? "—"}</td>
                  <td>{c.avg_er != null ? `${c.avg_er}%` : "—"}</td>
                  <td>
                    <span className="inline-flex items-center gap-1.5">
                      <span className={`h-1.5 w-1.5 rounded-full ${DOT[c.last_status ?? "idle"] ?? "bg-slate-300"}`} />
                      {c.last_agent || "—"}
                    </span>
                  </td>
                  <td>{c.pending_review}</td>
                  <td><Link href={`/channels/${c.id}`} className="text-xs text-brand hover:underline">open →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
