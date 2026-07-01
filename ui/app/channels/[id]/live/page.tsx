"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ControlState } from "@/lib/types";
import { ErrorBox, PageHeader, Spinner } from "@/components/ui";
import { AgentStream, PipelineFlow, SystemPanel } from "@/components/control";

const POLL_MS = 4000;

export default function LivePage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<ControlState | null>(null);
  const [error, setError] = useState("");
  const [running, setRunning] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try { setState(await api.control(id)); } catch (e) { setError(String(e)); }
  }, [id]);

  useEffect(() => {
    load();
    timer.current = setInterval(load, POLL_MS);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [load]);

  async function onRun(agent: string) {
    setRunning(agent);
    try { await api.runAgent(id, agent); await load(); }
    catch (e) { setError(String(e)); }
    finally { setTimeout(() => setRunning(""), 2000); }
  }
  async function onCancel(agent: string) {
    try { await api.cancelAgent(id, agent); await load(); } catch (e) { setError(String(e)); }
  }

  if (error) return <ErrorBox error={error} />;
  if (!state) return <Spinner />;

  return (
    <div>
      <PageHeader title="Live agent status" subtitle="Real-time pipeline, activity and system health (updates every 4s)." />
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-4"><SystemPanel system={state.system} channelId={id} onRun={onRun} running={running} /></div>
        <div className="lg:col-span-5"><PipelineFlow pipeline={state.pipeline} onCancel={onCancel} /></div>
        <div className="lg:col-span-3"><AgentStream events={state.events} /></div>
      </div>
    </div>
  );
}
