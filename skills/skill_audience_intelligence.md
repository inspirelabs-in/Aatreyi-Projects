# Skill: Audience Intelligence

## Purpose

Build a behavioral profile of the channel's audience — who they are, what they want, how they engage, and when they are active — using only observable signals from post and engagement data. This profile informs optimal posting times, content prioritization, and the framing of recommendations.

Telegram does not expose demographic data. This skill works entirely from behavioral inference: the agent reasons from what the audience *does* (reads, reacts to, forwards, ignores) to understand who they are and what they value.

---

## When This Skill Runs

- Every weekly pipeline run (audience behavior shifts over time)
- On-demand when the operator requests an audience analysis

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 output | Category, subcategory, audience type, primary goal |
| `posts` | Data collection | Full post history with text, media type, links |
| `engagement_data` | Data collection | Per-post views, forwards, reactions by type, reply counts |
| `subscriber_time_series` | Data collection | Subscriber count over time |
| `posting_timestamps` | Data collection | When each post was published |
| `audience_activity_heatmap` | Telegram API (admin channels) | Hourly activity distribution if available |

---

## Analysis Dimensions

### 1. Audience Intent

What is the audience trying to get from this channel? Intent is inferred by examining the content categories that generate the highest engagement relative to their posting frequency.

| Intent Type | Signal |
|---|---|
| Deal-seeking | High forwards and clicks on price/product posts |
| Information-gathering | High views on informational text posts; low reaction rate (reads and moves on) |
| Entertainment | High reactions (laughs, hearts) on casual content; high forwarding |
| Learning | High save-equivalent behavior (inferred from repeat engagement on educational posts) |
| Community belonging | High reply rate; high reactions on conversational or opinion posts |
| Signal-following | High click-through on specific call-to-action posts (links, alerts) |

A channel's audience may exhibit multiple intent types across different content categories.

### 2. Engagement Behavior Profile

Classifies the audience along two axes:

**Axis 1 — Engagement Depth:**
- Passive Consumer: Opens posts but rarely reacts, forwards, or replies
- Reactive: Reads and reacts (emoji responses) but rarely forwards
- Advocate: Forwards content to others — the most valuable audience behavior for growth

**Axis 2 — Response Consistency:**
- Consistent: Engages similarly across content categories
- Selective: Engages strongly with specific categories and ignores others

The combination of these axes produces the audience engagement profile, which directly shapes content prioritization recommendations.

### 3. Content Preference Map

Which content categories, formats, and topics produce above-average engagement, and by how much. This is built from the content intelligence scores but interpreted through the audience lens — not "what content performs best" but "what content this audience most values."

Distinctions that matter:
- A category may get high views but low forwards (the audience reads it but does not see it as worth sharing)
- A category may get low views but high reaction rates (the audience who does read it finds it highly valuable — it may be underexposed)
- A category may get high forwards but low reactions (widely shared but not emotionally resonant)

Each of these patterns implies a different strategic use for that content category.

### 4. Peak Activity Windows

When the audience is most likely to see and engage with posts. Derived from two signals:

**Primary signal — audience activity heatmap:** Available for admin-access channels. Shows the hourly distribution of audience activity across the past 7 days.

**Fallback signal — post performance by time:** When the heatmap is unavailable, the agent analyzes engagement data across all posts, groups by hour of posting and day of week, and identifies which time windows produce above-average view rates in the first 2 hours after posting (the critical window when most Telegram engagement occurs).

Output: a ranked list of posting windows by expected performance, broken down by day of week.

### 5. Audience Retention Signal

Is the audience growing, stable, or eroding? Inferred from:
- Reach percentage trend (are existing subscribers viewing fewer posts over time?)
- Reaction rate trend (are the subscribers who do open posts engaging less?)
- Subscriber growth vs. subscriber loss events (net retention trajectory)

This dimension feeds directly into the retention analysis stage.

### 6. Audience Sensitivity to Posting Frequency

Does increasing post volume hurt or help engagement? Derived by correlating posting frequency windows with reach percentage. If weeks with higher post counts show lower per-post reach, the audience is sensitive to overposting — a key retention risk factor.

---

## Audience Segments

For channels with more than 10,000 subscribers and sufficient content diversity, the agent identifies whether the audience contains distinct behavioral segments responding to different content categories. This is relevant for channels that cover multiple topics or product categories.

Example for a deals channel:
- **Segment A** — Engages primarily with electronics deals; forwards frequently; active evenings
- **Segment B** — Engages primarily with fashion deals; reacts with hearts; active afternoons
- **Segment C** — Engages broadly across all categories; consistently high engagement; core audience

If segments are detected, content recommendations are framed around serving the highest-value segment (typically the advocacy segment that forwards content) while maintaining sufficient coverage to retain the passive consumer segment.

---

## Outputs

```
audience_profile:
  primary_intent: string               # Main reason audience follows the channel
  secondary_intents: [string]          # Additional intent types observed
  engagement_behavior: string          # Passive / Reactive / Advocate (dominant type)
  response_consistency: string         # Consistent / Selective
  content_preferences:
    high_value: [string]               # Content categories this audience most values
    low_value: [string]                # Categories with low engagement from this audience
    underexposed: [string]             # High engagement-rate categories shown infrequently
  peak_activity_windows:
    - day: string
      hours: [int]                     # Hours in 24h format
      confidence: string               # High / Medium / Low
  frequency_sensitivity: string        # High / Medium / Low — sensitivity to overposting
  audience_segments: [object]          # Populated if distinct segments detected, else empty
  retention_signal: string             # Growing / Stable / Eroding
  inference_quality: string            # Data-rich / Data-limited / Insufficient
```

---

## Inference Quality Classification

| Quality Level | Criteria |
|---|---|
| Data-rich | Heatmap available + 200+ posts with engagement data |
| Data-limited | No heatmap but 100+ posts with engagement data |
| Insufficient | Fewer than 50 posts or fewer than 30 days of data |

When inference quality is `Insufficient`, the audience profile is flagged as preliminary and the daily plan will not include audience-timing recommendations until sufficient data is collected.

---

## Downstream Dependencies

`audience_profile` is used by:

- **Stage 4 (Content Intelligence)** — content scoring weights are adjusted based on audience engagement behavior type (Advocates are scored on forwards; Passive Consumers are scored on views)
- **Stage 7 (Growth Analysis)** — audience growth drivers are interpreted relative to audience intent
- **Stage 8 (Retention Analysis)** — retention thresholds and fatigue indicators are calibrated against the audience's baseline engagement behavior
- **Stage 10 (Recommendation Engine)** — daily posting time recommendations, content category prioritization, and engagement tactic selection all draw from `audience_profile`
