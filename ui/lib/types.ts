export interface ChannelSummary {
  id: string;
  telegram_username: string;
  display_name: string | null;
  tier: string | null;
  category: string | null;
  status: string | null;
}

export interface Dashboard {
  channel: {
    id: string;
    telegram_username: string;
    display_name: string | null;
    tier: string | null;
    category: string | null;
    status: string | null;
    needs_strategy_review: boolean;
  };
  kpis: {
    subscriber_count: number | null;
    avg_er: number | null;
    post_frequency_per_day: number | null;
    best_post_hour: number | null;
    subscriber_delta: number | null;
    subscriber_delta_pct: number | null;
    pending_review: number;
  };
  insights: { type: string; note: string }[];
  timeline: { task_id: string; time: string | null; format: string | null; topic: string | null; status: string | null }[];
}

export interface QueueItem {
  generated_post_id: string;
  post_text: string | null;
  post_format: string | null;
  media_url: string | null;
  link_url: string | null;
  poll_options: string[] | null;
  cta: string | null;
  hashtags: string[] | null;
  review_status: string;
  scheduled_at: string | null;
  created_at: string | null;
}

export interface ContentSourceRow {
  id: string;
  type: string;
  url: string | null;
  name: string | null;
  category: string | null;
  is_active: boolean;
  avg_quality_score: number;
  total_items_scored: number;
}

export interface ChannelSettings {
  channel_id: string;
  auto_approve: boolean;
  score_threshold: number;
}

export interface AnalyticsPoint {
  period_end: string | null;
  subscriber_count: number | null;
  subscriber_delta: number | null;
  subscriber_delta_pct: number | null;
  avg_views: number | null;
  avg_er: number | null;
  total_posts: number | null;
  churn_signal: boolean;
  insights: { type: string; note: string }[];
}

export interface Strategy {
  strategy_id: string;
  strategy_type: string | null;
  goal: string | null;
  post_frequency_per_day: number | null;
  content_mix: { format: string; pct: number }[] | null;
  primary_topics: string[] | null;
  growth_tactics: { tactic: string; detail: string; why?: string; action?: string; severity?: string }[] | null;
  diagnosis?: string | null;
  benchmark?: { competitor_avg_er: number | null; my_avg_er: number | null; target_er: number | null } | null;
  fatigue?: { score: number; flags: string[] } | null;
  competitor_insights?: { username: string; topic_similarity: number; content_similarity: number; avg_er: number | null; top_themes: string[]; recommendation: string }[] | null;
  period_start: string | null;
  period_end: string | null;
  tasks: { task_id: string; date: string | null; time: string | null; format: string | null; topic: string | null; kind?: string | null; status: string | null }[];
}

export interface AgentEvent {
  id: string;
  agent: string;
  label: string;
  icon: string;
  action: string;
  result: string;
  status: "done" | "running" | "failed" | string;
  ts: string | null;
  reason: string | null;
  duration_ms: number | null;
}

export interface PipelineAgent {
  agent: string;
  label: string;
  icon: string;
  steps: string[];
  status: "idle" | "running" | "done" | "failed" | string;
  last_run: string | null;
  duration_ms: number | null;
  summary: string;
}

export interface SystemState {
  subscriber_count: number | null;
  growth_rate: number | null;
  retention_trend: "up" | "down" | "flat" | string;
  engagement_pulse: number | null;
  churn_risk: "high" | "low" | string;
  churn_type: "spike" | "sustained" | null;
  agent_health: "green" | "yellow" | "red" | string;
  thinking: boolean;
  subscribers_updated_at?: string | null;
  subscriber_samples?: number;
}

export interface ControlState {
  channel: { id: string; telegram_username: string | null; display_name: string | null; tier: string | null; category: string | null };
  events: AgentEvent[];
  pipeline: PipelineAgent[];
  system: SystemState;
}

// ── admin (cross-tenant) ──
export interface AdminOverview {
  channels: number; agent_runs: number; failed_runs: number;
  running_now: number; pending_review: number; success_rate: number | null;
}

export interface AdminChannelRow {
  id: string; telegram_username: string; display_name: string | null;
  tier: string | null; category: string | null; status: string | null;
  subscriber_count: number | null; avg_er: number | null;
  last_agent: string | null; last_activity: string | null; last_status: string | null;
  pending_review: number;
}

export interface AgentPerf {
  agent: string; label: string; icon: string;
  runs: number; failed: number; success_rate: number | null; avg_ms: number | null;
}

export interface GlobalEvent extends AgentEvent {
  channel: string | null;
  channel_id: string | null;
}

export interface SystemHealth {
  channel_health: { channel: string | null; channel_id: string; health: string; runs: number }[];
  recent_failures: { agent: string; channel: string | null; error: string; ts: string | null }[];
}

export interface SubscriberPoint {
  ts: string | null;
  subscriber_count: number | null;
  delta: number | null;
}

export interface Intelligence {
  intelligence: {
    posts_analyzed?: number;
    purpose_mix?: Record<string, number>;
    spikes?: number;
    format_engagement?: { label: string; avg_er: number; posts: number }[];
    topic_engagement?: { label: string; avg_er: number; posts: number }[];
    community_signal?: {
      reaction_density: number; forward_rate: number;
      poll_participation: number | null; silent: boolean; state: string;
    };
    recycle_candidates?: { text_preview: string; er: number; suggestion: string }[];
  };
  retention_plan: { kind: string; format: string | null; topic: string; date: string | null; status: string | null }[];
}

export interface Competitor {
  competitor_username: string;
  display_name: string | null;
  subscriber_count: number | null;
  avg_er: number | null;
  post_frequency_per_day: number | null;
  top_content_themes: string[] | null;
  rank: number | null;
  rank_score: number | null;
  source: string | null;
  has_disappearing_messages: boolean;
}
