# Agent Orchestration — Telegram Growth & Retention Agent

## Overview

The Telegram Growth & Retention Agent is an AI-powered intelligence platform that connects to a Telegram channel, collects data from internal and external sources, runs a structured multi-stage analysis pipeline, and delivers growth plans, retention diagnostics, competitive intelligence, alerts, and recommendations — automatically and continuously.

This document defines the full orchestration logic: how the agent is triggered, how skills are sequenced, how data flows between stages, how outputs are assembled, and how the agent improves over time through outcome tracking.

---

## System Design Philosophy

The agent is not a reporting tool. It does not present raw data for a human to interpret. It acts as an intelligent analyst that interprets data, identifies what matters, and delivers decisions and actions directly to the channel operator.

Every stage of the pipeline is designed around a single question: **does this output tell the operator something specific they can act on?** If not, it is not surfaced.

The agent operates on three time horizons simultaneously:
- **Immediate** — real-time alerts when something significant happens
- **Daily** — a focused action plan for the next 24 hours
- **Weekly** — a full strategic review with performance retrospective and forward plan

---

## User Input

The operator provides the following at setup:

| Input | Type | Required |
|---|---|---|
| Telegram API ID | Numeric credential from my.telegram.org | Mandatory |
| Telegram API Hash | Secret key from my.telegram.org | Mandatory |
| Channel Username, URL, or ID | Channel identifier | Mandatory |
| Primary Goal | Growth / Engagement / Retention / Monetization | Optional |
| Known Competitor Channels | List of @usernames | Optional |
| Alert Preferences | Which alert types to enable | Optional |
| Reporting Time Zone | For scheduling daily/weekly delivery | Optional |

The agent uses the API ID and API Hash to authenticate via the Telegram MTProto API using the operator's own account identity. This provides read access to all channel data the operator can access. No bot token is required. No new account is created.

---

## Data Sources

### Internal Sources (via Telegram MTProto API)
- Channel profile metadata (name, description, subscriber count, creation date, category)
- Full post history — up to 1000 posts or last 180 days
- Per-post engagement — views, forwards, reactions by type, reply counts
- Subscriber growth time series
- Audience activity heatmap (for admin-access channels)
- Stories and story metrics where available

### External Sources
| Source | Primary Use |
|---|---|
| TGStat API | Competitor discovery, competitor growth history, category rankings, top post data |
| Telemetr.io API | Secondary competitor discovery, audience overlap scoring, ad mention intelligence |
| Telegram MTProto Search | Supplementary competitor discovery — catches fast-growing channels not yet in databases |
| Public Channel Directories | Fallback competitor discovery for niche categories with low TGStat coverage |

---

## Pipeline Architecture

The pipeline consists of 12 sequential stages. Each stage consumes the outputs of preceding stages and contributes to a shared **Channel Intelligence Context** object that accumulates understanding throughout the run.

```
User Connects Telegram
        ↓
[Stage 1]  Data Collection & Cleaning
        ↓
[Stage 2]  Channel Classification
        ↓
[Stage 3]  Audience Intelligence
        ↓
[Stage 4]  Content Intelligence
        ↓
[Stage 5]  Competitor Intelligence
        ↓
[Stage 6]  Benchmark Engine
        ↓
[Stage 7]  Growth Analysis
        ↓
[Stage 8]  Retention Analysis
        ↓
[Stage 9]  Alert Engine
        ↓
[Stage 10] Recommendation Engine
        ↓
[Stage 11] Outcome Tracking
        ↓
[Stage 12] Report & Dashboard Assembly
```

---

## Stage-by-Stage Orchestration

### Stage 1 — Data Collection & Cleaning

**Trigger:** Scheduled refresh (every 6 hours for channel data; every 24 hours for competitor data) or on-demand.

**What happens:**
The agent connects to Telegram via the MTProto API using the stored session. It fetches all new posts since the last collection run, updates engagement data on recent posts (views and reactions continue accumulating after posting), refreshes the subscriber count snapshot, and pulls updated competitor stats from TGStat and Telemetr.io.

Raw data is cleaned before being passed downstream: duplicate posts are removed, encoding issues in post text are normalized, engagement values are validated for consistency (e.g. forwards cannot exceed views), and outlier posts caused by cross-posting spam are flagged.

**Output passed to next stage:** Clean, structured dataset of posts with engagement, subscriber time series, and competitor raw data.

---

### Stage 2 — Channel Classification

**Skill:** `skill_channel_classification`
**Prompt:** `prompt_channel_classification`

**What happens:**
Claude analyzes the channel's name, description, and a sample of 50 recent posts to classify the channel. Classification is multi-level: a primary category (e.g. Deals & Affiliate, News & Media, Education, Entertainment, Finance, Health, Community), a subcategory (e.g. within Deals: Mobile Accessories, Electronics, Fashion), a geographic focus (local, national, global), and a channel maturity stage (new under 6 months, growing, established, mature).

The classification also identifies the channel's implicit primary goal (growth, engagement, clicks, community) and its dominant content style (text-heavy, media-heavy, link-heavy, mixed).

This classification profile is injected into the Channel Intelligence Context and used by every downstream stage to ensure all analysis is appropriate for this specific channel type.

**Output added to context:** `channel_profile` — category, subcategory, geography, maturity, primary goal, content style, audience type.

---

### Stage 3 — Audience Intelligence

**Skill:** `skill_audience_intelligence`
**Prompt:** `prompt_audience_intelligence`

**What happens:**
Claude infers the audience profile from three signals: the content the channel publishes (what topics and products it covers implies what the audience cares about), the engagement patterns (what content gets the most reactions and forwards reveals what the audience responds to emotionally), and the posting time performance (when the audience is most active, inferred from which posting windows produce above-average views).

Since Telegram does not expose demographic data, all audience intelligence is inferred. The agent builds a behavioral audience profile — not demographic — covering audience intent (what they are trying to get from this channel), engagement behavior (passive consumers vs. active reactors vs. advocates who forward), content preferences by category, and estimated peak activity windows.

**Output added to context:** `audience_profile` — intent, behavior type, content preferences, peak activity windows, inferred interests.

---

### Stage 4 — Content Intelligence

**Skill:** `skill_content_intelligence`
**Prompt:** `prompt_content_intelligence`

**What happens:**
Every post in the dataset is categorized into the channel's specific content taxonomy — not a generic taxonomy, but one derived from what this channel actually posts. A deals channel's taxonomy differs from a news channel's taxonomy, and the agent builds the right one for each channel.

Each content category is then scored using a composite engagement signal. The scoring weights forwards and reactions more heavily than raw views, because forwards represent active advocacy (the audience values the content enough to share it) and reactions represent emotional resonance — both are stronger growth indicators than passive views.

The scoring also identifies: the best-performing post in each category (as a reference example), the worst-performing post in each category, the optimal post length and media type by category, and underutilized categories (content types that perform well when used but appear infrequently in the posting history).

**Output added to context:** `content_intelligence` — category taxonomy, performance scores by category, best/worst examples, optimal format per category, underutilized opportunities.

---

### Stage 5 — Competitor Intelligence

**Skill:** `skill_competitor_intelligence`
**Prompt:** `prompt_competitor_intelligence`

**What happens:**
This stage runs on a 24-hour independent cycle and feeds its results into every subsequent analysis stage.

**Competitor Discovery:** Using the channel classification and content taxonomy from Stages 2 and 4, the agent extracts 3–5 niche keywords and searches TGStat, Telemetr.io, and Telegram search in parallel. Candidate channels are filtered by size proximity (30%–1000% of the user's subscriber count), recency (last post within 14 days), and language match. Surviving candidates are ranked by category match score and recent growth velocity. The top 5 are selected as tracked competitors. User-specified competitors are always included.

**Competitor Enrichment:** For each tracked competitor, the agent collects: current subscriber count and 7-day growth delta, average views and engagement rate for the last 30 posts, content type distribution (text/photo/video/poll breakdown), posting frequency and timing patterns, and the top 3 performing posts from the last 7 days.

**Competitor Intelligence Analysis:** Claude analyzes the enriched competitor data to identify: what content strategies competitors are using that the user's channel is not, which competitors are growing fastest and what is driving that growth, whether any competitor has recently changed their strategy, and what the market is converging toward in terms of content format and frequency.

**Output added to context:** `competitor_intelligence` — tracked competitors with full stats, content strategy profiles, growth patterns, identified competitive gaps, competitor strategy changes.

---

### Stage 6 — Benchmark Engine

**Skill:** `skill_benchmark_engine`
**Prompt:** `prompt_benchmark_engine`

**What happens:**
The benchmark engine places the channel's performance in context by comparing it against three reference groups constructed from the competitor dataset and TGStat category data:

- **Industry Benchmark** — the full category average across all channels of similar type
- **Peer Benchmark** — the average across the 5 tracked competitors (most similar channels)
- **Top Performer Benchmark** — the metrics of the top 10% of channels in the category

For each benchmark, the engine computes a percentile rank for: subscriber growth rate, average reach percentage, engagement rate (ER), engagement rate by reach (ERR), posting frequency, and content diversity score.

Metrics are normalized before comparison to remove size distortion — a 10,000-subscriber channel and a 200,000-subscriber channel are not directly comparable on raw numbers but are comparable on normalized rates.

**Output added to context:** `benchmark_results` — percentile scores for each metric across all three benchmark types, gap scores vs. peer average and top performer average, competitive position classification per metric (leading / on-par / lagging).

---

### Stage 7 — Growth Analysis

**Skill:** `skill_growth_analysis`
**Prompt:** `prompt_growth_analysis`

**What happens:**
The growth analysis module answers three questions: why is the channel growing (or not), what is blocking growth, and what specific actions would accelerate growth.

It does this by correlating the subscriber time series with the content dataset — looking for statistical relationships between posting behavior and subscriber trajectory. It identifies: which content categories and post types precede above-average subscriber gain; which behaviors (over-posting, repetitive content, long gaps) precede subscriber loss; the current growth rate trend (accelerating, stable, or decelerating); and how the channel's growth rate compares to benchmark percentiles.

The output is organized into three outputs: **growth drivers** (what is currently working for growth), **growth bottlenecks** (what is currently suppressing growth), and **growth opportunities** (what the channel could do that competitors are doing successfully).

A composite **Growth Score** (0–100) is computed from: growth rate vs. peer benchmark, growth rate trend direction, content-to-growth correlation strength, and posting consistency.

**Output added to context:** `growth_analysis` — growth score, growth drivers, growth bottlenecks, growth opportunities, growth rate vs. benchmark.

---

### Stage 8 — Retention Analysis

**Skill:** `skill_retention_analysis`
**Prompt:** `prompt_retention_analysis`

**What happens:**
Retention analysis measures whether existing subscribers are becoming more or less engaged over time — a leading indicator of future subscriber loss.

The primary retention metric is **reach percentage** — the share of subscribers who view each post. A declining reach percentage means existing subscribers are progressively less likely to open the channel's posts, which is the early signal of audience fatigue. The module computes a rolling 7-day and 30-day reach percentage average, calculates the trend direction, and models the decay rate if the trend is negative.

The module then tests the most common causes of reach decline against the channel's data: posting frequency increase without engagement increase (content saturation), repetitive content category dominance (format fatigue), sustained reaction rate decline (content quality drift), and inconsistent posting schedule (expectation disruption).

It also computes the **Engagement Rate by Reach (ERR)** trend — which captures whether the subscribers who *do* open posts are finding them valuable, separate from the reach question.

A composite **Retention Score** (0–100) is computed from: reach percentage vs. peer benchmark, reach trend direction, ERR trend, audience fatigue signal strength, and posting consistency score.

**Output added to context:** `retention_analysis` — retention score, reach % trend, ERR trend, identified fatigue signals, retention risks by severity, probable causes, recommended interventions.

---

### Stage 9 — Alert Engine

**Skill:** `skill_alert_engine`
**Prompt:** `prompt_alert_generation`

**What happens:**
The alert engine runs on a continuous 30-minute monitoring cycle, independent of the main analysis pipeline. It evaluates current metrics against a set of defined thresholds and dispatches alerts when thresholds are breached.

Alert types are organized into five categories:

**Growth Alerts**
- Growth Drop: growth rate falls below 50% of 30-day average
- Growth Spike: growth rate exceeds 200% of 30-day average (positive signal to capitalize on)

**Reach Alerts**
- Reach Drop: average reach % falls 20%+ below 7-day rolling average within a 24-hour window
- Reach Spike: a post reaches 3x+ average views within 6 hours of posting

**Engagement Alerts**
- ER Drop: engagement rate falls below 60% of 7-day average
- ERR Drop: engagement rate by reach falls below 60% of 7-day average (audience quality signal)

**Retention Alerts**
- Audience Fatigue: reach % has declined for 5 consecutive days
- Retention Risk: retention score drops below threshold (configurable, default: 40/100)

**Competitor Alerts**
- Competitor Growth Spike: a tracked competitor gains 2%+ subscribers in 24 hours
- Competitor Strategy Change: a tracked competitor's content type distribution shifts significantly

**Opportunity Alerts**
- Trending Topic: a content topic is gaining momentum across tracked competitor channels
- Content Gap: an underutilized category is showing high performance signals

Each alert contains: the metric that triggered it, current value versus threshold, probable cause derived from recent data, a specific recommended action, and a severity level (Critical / Warning / Opportunity / Info).

**Output:** Alerts dispatched immediately via Telegram message to the operator. Alerts also written to the alert log for inclusion in the weekly report.

---

### Stage 10 — Recommendation Engine

**Skill:** `skill_recommendation_engine`
**Prompt:** `prompt_recommendation_generation`

**What happens:**
The recommendation engine synthesizes the outputs of all preceding stages into a prioritized action plan. It operates on three time horizons:

**Daily Plan** (generated every morning):
A short, specific list of 3–5 actions for the current day. Includes: recommended post count and optimal posting windows based on audience activity data, specific content category to focus on today with rationale drawn from content intelligence, whether to include an engagement element (poll, question, reaction prompt) based on retention health, and one corrective action if any metric is in alert state.

**Weekly Recommendations** (generated with weekly report):
The top 5 prioritized strategic recommendations for the coming week. Each recommendation is structured as:
- **Title** — a clear, specific action (not a vague suggestion)
- **Priority** — ranked 1–5
- **Confidence** — how strongly the evidence supports this recommendation (High / Medium / Low)
- **Expected Impact** — which metric this addresses and by how much (estimated)
- **Evidence** — the specific data points that support this recommendation
- **Action** — step-by-step what to do
- **Timeline** — when to implement
- **Success Metric** — how to know it worked

Recommendations are drawn from: content opportunities (underutilized high-performing categories), growth opportunities (competitor strategies not yet used by this channel), retention interventions (actions to address identified fatigue or reach decline), and engagement improvements (format or timing changes supported by benchmark data).

**Output:** Daily plan delivered as a Telegram message. Weekly recommendations included in the weekly report and passed to the Outcome Tracking stage.

---

### Stage 11 — Outcome Tracking

**Skill:** `skill_outcome_tracking`
**Prompt:** `prompt_outcome_tracking`

**What happens:**
Outcome tracking closes the feedback loop. Every recommendation generated by Stage 10 is tracked through a defined lifecycle:

```
Generated → Accepted → Implemented → Measured → Successful / Failed / Inconclusive
```

When a recommendation is generated, its baseline metrics are recorded (the current values of the metrics it aims to improve). The agent monitors the channel over the subsequent 7–14 days and compares the after-metrics to the baseline.

A recommendation is marked **Successful** if the target metric improved by at least the minimum expected impact within the measurement window. It is marked **Failed** if the metric did not improve or worsened. It is marked **Inconclusive** if external factors (e.g. a competitor spike or a Telegram-wide reach drop) prevent clean attribution.

The outcome data is used in two ways:
1. **Immediate feedback** — the weekly report shows the operator which recommendations from last week worked, which did not, and what the measured impact was.
2. **Learning** — the recommendation engine uses outcome history to calibrate its confidence scores. Recommendations of a certain type that have historically failed for this channel type are downweighted; recommendations that have historically succeeded are prioritized.

**Output added to context:** `outcome_history` — recommendation outcomes with before/after metrics, success rate by recommendation category, confidence calibration adjustments.

---

### Stage 12 — Report & Dashboard Assembly

**What happens:**
The report assembly stage packages all intelligence into structured outputs for delivery. Three report types are produced:

**Daily Action Plan** (delivered every morning via Telegram):
- Today's recommended post count and optimal windows
- Content focus for the day with rationale
- Any active alerts requiring attention
- One improvement action if a metric is in warning state

**Weekly Strategic Report** (delivered every Monday):
- Channel Health Score (composite of Growth Score + Retention Score + Benchmark Percentile)
- Growth Report: growth score, trend, drivers, bottlenecks, vs. benchmark
- Retention Report: retention score, reach trend, ERR trend, fatigue assessment
- Competitor Report: all 5 tracked competitors with week-over-week changes
- Benchmark Summary: percentile position across all key metrics
- Top 5 Recommendations with full evidence and action detail
- Outcome Review: what last week's recommendations achieved
- Alert Log: all alerts fired in the past 7 days with resolutions

**On-Demand Reports** (triggered by operator command):
- Post performance analysis (last N posts)
- Head-to-head competitor comparison
- Metric diagnosis (why did X drop?)
- Content strategy snapshot

---

## Scheduling

| Job | Frequency | What Runs |
|---|---|---|
| Channel Data Refresh | Every 6 hours | Stage 1 (channel data only) |
| Competitor Data Refresh | Every 24 hours | Stage 1 (competitor data) + Stage 5 |
| Alert Monitor | Every 30 minutes | Stage 9 |
| Daily Analysis + Plan | Every day at 6:00 AM (operator's TZ) | Stages 1–10, Daily Plan output |
| Weekly Report | Every Monday at 7:00 AM (operator's TZ) | Full pipeline, Weekly Report output |
| Competitor Discovery | Every 7 days | Competitor discovery sub-routine in Stage 5 |
| Outcome Measurement | Every 7 days per active recommendation | Stage 11 |

---

## Channel Intelligence Context Object

The context object is the shared state that accumulates across all pipeline stages in a single run. Each stage reads from it and writes to it. At the end of a full pipeline run, the context represents the complete intelligence picture of the channel.

| Key | Set By Stage | Used By Stages |
|---|---|---|
| `channel_profile` | Stage 2 | All downstream stages |
| `audience_profile` | Stage 3 | 4, 7, 8, 10 |
| `content_intelligence` | Stage 4 | 5, 6, 7, 8, 10 |
| `competitor_intelligence` | Stage 5 | 6, 7, 10 |
| `benchmark_results` | Stage 6 | 7, 8, 10, 12 |
| `growth_analysis` | Stage 7 | 9, 10, 12 |
| `retention_analysis` | Stage 8 | 9, 10, 12 |
| `alerts` | Stage 9 | 10, 12 |
| `recommendations` | Stage 10 | 11, 12 |
| `outcome_history` | Stage 11 | 10 (feedback loop) |

---

## Error Handling

| Error Condition | Response |
|---|---|
| Telegram API rate limit | Exponential backoff, 3 retries. Mark data as stale if all fail. |
| TGStat / Telemetr unavailable | Use last cached data. Flag competitor section as stale in report. |
| Fewer than 50 posts available | Proceed with reduced confidence. Flag affected sections. |
| Competitor discovery returns zero | Broaden filter, re-query. Fall back to category-level benchmark. |
| AI stage failure | Log error, skip stage, mark output fields as unavailable. Continue pipeline. |
| Session expiry | Pause all jobs. Alert operator to re-authenticate. |
| Recommendation with no measurable metric | Mark as untrackable. Exclude from outcome learning loop. |

---

## Agent Improvement Over Time

The agent is designed to improve its recommendation quality continuously through the outcome tracking loop. As more recommendation outcomes are recorded for a channel, the recommendation engine gains a calibrated picture of what works for that specific channel type, niche, and audience. Confidence scores on future recommendations are adjusted accordingly.

This means a channel that has been connected for 3 months will receive more accurate and higher-confidence recommendations than it did in week one — the agent learns the channel's specific dynamics over time.
