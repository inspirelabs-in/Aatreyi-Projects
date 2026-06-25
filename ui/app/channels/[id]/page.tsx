"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { ControlState } from "@/lib/types";
import { Badge, ErrorBox, Spinner } from "@/components/ui";
import { AgentStream, PipelineFlow, SystemPanel } from "@/components/control";

const POLL_MS = 4000;

export default function ControlRoomPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<ControlState | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.control(id));
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  async function onRun(agent: string) {
    setRunning(agent);
    try {
      await api.runAgent(id, agent, agent === "analytics" ? { snapshot_type: "daily" } : {});
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning("");
    }
  }

  async function onCancel(agent: string) {
    try {
      await api.cancelAgent(id, agent);
      await load();
    } catch (e) {
      setError(String(e));
    }
  }

  if (error && !data) return <ErrorBox error={error} />;
  if (!data) return <Spinner label="Connecting to control room…" />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold text-slate-900">🧠 Control Room</h1>
        <span className="text-sm text-slate-500">@{data.channel.telegram_username}</span>
        {data.channel.tier && <Badge tone="blue">{data.channel.tier}</Badge>}
        {data.channel.category && <Badge>{data.channel.category}</Badge>}
        <span className="ml-auto flex items-center gap-1.5 text-xs text-slate-400">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-green-500" /> live · refreshing every {POLL_MS / 1000}s
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <div className="lg:col-span-3"><AgentStream events={data.events} /></div>
        <div className="lg:col-span-6"><PipelineFlow pipeline={data.pipeline} onCancel={onCancel} /></div>
        <div className="lg:col-span-3"><SystemPanel system={data.system} channelId={id} onRun={onRun} running={running} /></div>
      </div>
    </div>
  );
}
