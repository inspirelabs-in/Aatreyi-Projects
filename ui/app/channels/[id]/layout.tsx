"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ChannelSummary } from "@/lib/types";
import { Badge } from "@/components/ui";
import { RunAgents } from "@/components/RunAgents";

export default function ChannelLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const [ch, setCh] = useState<ChannelSummary | null>(null);

  useEffect(() => {
    api.listChannels().then((cs) => setCh(cs.find((c) => c.id === id) || null)).catch(() => setCh(null));
  }, [id]);

  return (
    <div>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-edge pb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-bold text-slate-900">{ch ? `@${ch.telegram_username}` : "Channel"}</h2>
          {ch?.tier && <Badge tone="blue">{ch.tier}</Badge>}
          {ch?.category && <Badge>{ch.category}</Badge>}
          {ch?.status && <Badge tone="amber">{ch.status}</Badge>}
        </div>
        <RunAgents channelId={id} />
      </div>
      {children}
    </div>
  );
}
