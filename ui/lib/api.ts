import type {
  AdminChannelRow, AdminOverview, AgentPerf, AnalyticsPoint, ChannelSettings, ChannelSummary,
  Competitor, ContentSourceRow, ControlState, Dashboard, GlobalEvent, Intelligence, QueueItem,
  Strategy, SubscriberPoint, SystemHealth,
} from "./types";
import { getRole } from "./role";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "X-Role": getRole(), ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}: ${detail}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const api = {
  listChannels: () => req<ChannelSummary[]>("/api/channels"),
  onboard: (body: { telegram_username: string; category?: string; growth_goal?: string }) =>
    req<{ channel_id: string }>("/api/channels", { method: "POST", body: JSON.stringify(body) }),

  dashboard: (id: string) => req<Dashboard>(`/api/channels/${id}/dashboard`),
  control: (id: string) => req<ControlState>(`/api/channels/${id}/control`),
  intelligence: (id: string) => req<Intelligence>(`/api/channels/${id}/intelligence`),
  queue: (id: string) => req<QueueItem[]>(`/api/channels/${id}/queue`),
  analytics: (id: string, type = "daily", n = 30) =>
    req<AnalyticsPoint[]>(`/api/channels/${id}/analytics?snapshot_type=${type}&n=${n}`),
  subscribers: (id: string, n = 300) =>
    req<SubscriberPoint[]>(`/api/channels/${id}/subscribers?n=${n}`),
  strategy: (id: string) => req<Strategy>(`/api/channels/${id}/strategy`),
  competitors: (id: string) => req<Competitor[]>(`/api/channels/${id}/competitors`),

  listSources: (id: string) => req<ContentSourceRow[]>(`/api/channels/${id}/sources`),
  addSource: (id: string, url: string, name?: string, type: "rss" | "website" = "rss") =>
    req(`/api/channels/${id}/sources`, { method: "POST", body: JSON.stringify({ type, url, name }) }),
  updateSource: (id: string, sourceId: string, body: { is_active?: boolean; name?: string; url?: string }) =>
    req(`/api/channels/${id}/sources/${sourceId}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteSource: (id: string, sourceId: string) =>
    req(`/api/channels/${id}/sources/${sourceId}`, { method: "DELETE" }),
  seedSources: (id: string) => req(`/api/channels/${id}/sources/seed`, { method: "POST" }),
  getSettings: (id: string) => req<ChannelSettings>(`/api/channels/${id}/settings`),
  updateSettings: (id: string, body: { auto_approve?: boolean; score_threshold?: number }) =>
    req<ChannelSettings>(`/api/channels/${id}/settings`, { method: "PATCH", body: JSON.stringify(body) }),

  approve: (id: string, postId: string) =>
    req(`/api/channels/${id}/queue/${postId}/approve`, { method: "POST" }),
  reject: (id: string, postId: string, reason?: string) =>
    req(`/api/channels/${id}/queue/${postId}/reject`, { method: "POST", body: JSON.stringify({ reason }) }),
  edit: (id: string, postId: string, edited_text: string) =>
    req(`/api/channels/${id}/queue/${postId}`, { method: "PUT", body: JSON.stringify({ edited_text }) }),

  runAgent: (id: string, agent: string, extra: Record<string, unknown> = {}) =>
    req<{ agent: string; status?: string; result?: unknown }>(`/api/channels/${id}/agents/run`, {
      method: "POST",
      body: JSON.stringify({ agent, ...extra }),
    }),

  // ── admin (system owner) ──
  adminOverview: () => req<AdminOverview>("/api/admin/overview"),
  adminChannels: () => req<AdminChannelRow[]>("/api/admin/channels"),
  adminPerformance: () => req<AgentPerf[]>("/api/admin/agent-performance"),
  adminEvents: (limit = 60) => req<GlobalEvent[]>(`/api/admin/global-events?limit=${limit}`),
  adminHealth: () => req<SystemHealth>("/api/admin/system-health"),
};
