// Central, user-facing explanations surfaced as ⓘ tooltips across the app, so
// anyone using the dashboard understands what each tab, agent, and signal means.

export const TAB_INFO: Record<string, string> = {
  "": "Live control room: watch agents run in real time, see the workflow pipeline, and trigger any agent manually.",
  queue: "Content Factory — every AI-generated post awaiting review. Approve to publish to Telegram, edit the copy, or reject. Shows each post's scheduled publish time.",
  sources: "Where content ideas come from: RSS feeds, websites, and the channel's own site. Also controls auto-approve (publish without manual review).",
  intelligence: "Deep post & audience signals: virality, forward/reaction density, post-purpose mix (growth/retention/conversion), and whether the community is engaged or silent.",
  analytics: "Performance over time: subscriber growth, engagement rate (ER), reach, and churn — as daily/weekly/monthly snapshots.",
  strategy: "The AI's plan for the channel: posting cadence, content-format mix, focus topics, growth tactics, and the per-slot posting schedule.",
  competitors: "Similar Telegram channels in your niche, ranked by topic overlap, with their engagement rates and top content themes used to benchmark you.",
};

export const AGENT_INFO: Record<string, string> = {
  onboard: "Full first-run pipeline for a channel: detects subscribers & tier, then runs DNA → competitor → analytics → strategy and backfills history.",
  dna: "Channel DNA: profiles the channel's category, topics, tone, posting cadence, best post hours, and format mix from its real posts.",
  competitor: "Discovers and qualifies similar Telegram channels, computes topic/content similarity, and pulls their engagement to benchmark you.",
  analytics: "Computes a performance snapshot: subscriber delta, average views/ER, reach, churn signal, and post intelligence.",
  strategy: "Builds the action plan — cadence, content mix, focus topics, growth tactics, and the per-slot posting schedule — from DNA + analytics + competitors.",
};

export const METRIC_INFO: Record<string, string> = {
  growth_rate: "Net subscriber change over roughly the last 24h, from high-frequency subscriber samples.",
  engagement_pulse: "Recent average engagement rate (reactions + forwards relative to views/subscribers).",
  retention: "Direction of audience retention: are subscribers sticking (up), holding (flat), or leaving (down).",
  churn_risk: "Risk that subscribers are leaving — graded none/low/medium/high from the subscriber trend. 'No data yet' until enough samples accumulate.",
};

export const SECTION_INFO = {
  agentStream: "A live feed of every agent action as it happens — what ran, the result, and any errors.",
  pipeline: "The multi-agent workflows (DNA, competitor, analytics, strategy, content) and their current run status.",
  manualTriggers: "Run any agent on demand instead of waiting for the daily/weekly schedule.",
  autoApprove: "When ON, approved posts publish to Telegram automatically (needs BOT_TOKEN and the bot as a channel admin). When OFF, posts wait in the Content Factory for manual review.",
  rss: "An RSS feed URL the content agent reads for fresh, on-topic articles to turn into posts.",
  website: "A website URL the content agent scrapes for content ideas — typically the channel's own site (e.g. for deals/products).",
  quality: "Running average quality score of items this source has produced (higher = more on-topic, engaging content).",
};
