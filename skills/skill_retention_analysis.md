# Skill: Retention Analysis

## Purpose

Measure whether existing subscribers are becoming more or less engaged over time, identify the causes of any deterioration, and provide early warning of audience fatigue before it becomes serious enough to cause subscriber loss. Retention problems are almost always detectable weeks before they cause visible damage — this skill finds them early.

---

## When This Skill Runs

- Every daily pipeline run (reach trend updated daily)
- Every weekly pipeline run (full retention analysis with causal diagnosis)

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 | Category, maturity, content style |
| `audience_profile` | Stage 3 | Engagement behavior, frequency sensitivity |
| `content_intelligence` | Stage 4 | Category scores, posting cadence, oversaturation flags |
| `benchmark_results` | Stage 6 | Reach % and ERR percentile ranks |
| `posts` + `engagement_data` | Data collection | Full post history with views, reactions, forwards |
| `subscriber_time_series` | Data collection | Subscriber count history |

---

## Core Retention Metrics

### Metric 1 — Reach Percentage

```
reach_percentage = post_views / subscriber_count × 100
```

This is the primary retention metric. It measures what fraction of existing subscribers are actively opening the channel's posts. A declining reach percentage means existing subscribers are increasingly choosing not to read the channel — the defining signal of disengagement.

**Why this matters more than view counts:** Total views can increase while reach percentage falls (if the subscriber count grows faster than engagement keeps pace). Reach percentage removes subscriber count growth from the equation and measures pure audience engagement quality.

### Metric 2 — Engagement Rate by Reach (ERR)

```
ERR = (reactions + forwards) / views × 100
```

ERR measures the quality of engagement among the subscribers who *do* open the posts. A falling ERR — even when reach % is stable — means the audience is reading but finding the content less valuable. This is a content quality signal, separate from the reach signal.

### Metric 3 — Reaction Rate

```
reaction_rate = reactions / views × 100
```

Tracks emotional resonance. A declining reaction rate across all content categories indicates that content is becoming less emotionally engaging — a leading indicator of audience drift.

### Metric 4 — Forward Rate

```
forward_rate = forwards / views × 100
```

Tracks audience advocacy. A declining forward rate means the audience is less likely to share content — which reduces both organic acquisition and is a retention signal (people share content they are excited about; they stop sharing content they have grown indifferent to).

---

## Analysis Framework

### Step 1 — Rolling Averages and Trend Calculation

For each metric, the agent computes:
- 7-day rolling average (short-term signal)
- 30-day rolling average (medium-term trend)
- Week-over-week change
- Month-over-month change
- Trend direction (Improving / Stable / Declining)
- Trend velocity (how fast it is changing)

### Step 2 — Audience Fatigue Detection

Audience fatigue is a state where the channel's existing subscribers have become desensitized to the content — they open fewer posts, react less, and are at elevated risk of unsubscribing. It builds gradually, not suddenly.

The agent tests for fatigue by looking for three concurrent signals:

**Signal 1 — Sustained reach decline:**
Reach percentage has declined for 5 or more consecutive days without a recovery day.

**Signal 2 — Content category saturation:**
One content category accounts for more than 40% of recent posts AND its per-post score trend is declining (the audience is seeing too much of the same thing).

**Signal 3 — Frequency-engagement mismatch:**
Posting frequency has increased (or remained high) while per-post engagement is declining — meaning more posts are producing less total engagement.

Fatigue is classified as:
- **Not detected** — none or one signal present
- **Emerging** — two signals present (early warning)
- **Active** — all three signals present (action required)

### Step 3 — Retention Risk Assessment

Beyond fatigue, the agent evaluates the channel for four retention risk factors:

**Risk 1 — Reach Decline Risk**
Present when: 30-day reach % trend is negative AND the rate of decline is accelerating.
This is the most serious retention risk — it means the problem is getting worse, not stabilizing.

**Risk 2 — Content Quality Drift**
Present when: ERR has declined for 3+ consecutive weeks across the majority of content categories.
This indicates the content mix has shifted away from what the audience finds valuable, regardless of posting volume.

**Risk 3 — Posting Inconsistency**
Present when: The standard deviation of daily post counts over the last 30 days is high AND engagement drops are correlated with gap periods.
Inconsistent posting disrupts the audience's expectation of the channel, leading to habit-breaking (they stop checking the channel regularly).

**Risk 4 — Single-Category Dependence**
Present when: One content category accounts for more than 60% of total engagement AND its score trend is declining.
The channel is over-reliant on a single content type. If that category's performance continues to decline, there is no other category to absorb the engagement — a structural fragility.

Each risk is rated as High, Medium, or Low based on severity and trend direction.

### Step 4 — Retention Score Computation

The Retention Score is a composite 0–100 score representing the overall health of audience retention.

| Component | Weight | How Scored |
|---|---|---|
| Current Reach % vs. Peer Benchmark | 30% | Peer percentile mapped to 0–100 |
| Reach % Trend Direction | 25% | Improving = 100, Stable = 70, Declining = 30, Accelerating Decline = 0 |
| ERR Trend Direction | 20% | Same scale as reach trend |
| Audience Fatigue Signal | 15% | Not Detected = 100, Emerging = 50, Active = 0 |
| Posting Consistency | 10% | High consistency = 100, Low consistency = 20 |

### Score Interpretation

| Score Range | Label | What It Means |
|---|---|---|
| 80–100 | Healthy | Audience is engaged and stable; no retention concerns |
| 60–79 | Good | Minor signals present; monitor but no immediate action required |
| 40–59 | At Risk | Retention is showing stress; action recommended within 2 weeks |
| 20–39 | Deteriorating | Retention is actively declining; action required immediately |
| 0–19 | Critical | Severe audience disengagement; structural intervention needed |

### Step 5 — Causal Diagnosis

For every identified risk or fatigue signal, the agent constructs a specific causal explanation based on the actual channel data — not a generic platitude.

Examples of specific diagnoses:
- "Reach percentage has declined 22% over the last 30 days. This correlates with a 3x increase in posting frequency during the same period. The audience is being shown too many posts, which reduces the perceived value of each post."
- "ERR has fallen 18% over 4 weeks despite stable reach. The content category driving this decline is Charger Deals, which has grown from 15% to 38% of all posts in the same period — repetitive content in this category is reducing engagement quality."
- "Posting gaps of 3+ days occurred 4 times in the last 30 days. Engagement in the 48 hours following each gap was 35% below the channel average, suggesting the audience loses the posting habit during gaps."

---

## Outputs

```
retention_analysis:
  retention_score: int                     # 0–100
  retention_score_label: string            # Healthy / Good / At Risk / Deteriorating / Critical
  
  metrics:
    reach_percentage_current: float
    reach_percentage_7d_avg: float
    reach_percentage_30d_avg: float
    reach_trend: string                    # Improving / Stable / Declining
    reach_decline_rate: float              # % change per week if declining
    
    err_current: float
    err_trend: string
    
    reaction_rate_trend: string
    forward_rate_trend: string
  
  audience_fatigue:
    status: string                         # Not Detected / Emerging / Active
    signals_present: [string]              # Which of the 3 signals are active
  
  retention_risks:
    - risk_type: string                    # Reach Decline / Content Quality Drift / etc.
      severity: string                     # High / Medium / Low
      evidence: string
      recommended_intervention: string
  
  retention_narrative: string              # Plain-language explanation with causal diagnosis
  
  immediate_actions: [string]              # Actions to take within 24–48 hours if severity is High
```

---

## Downstream Dependencies

`retention_analysis` is used by:

- **Stage 9 (Alert Engine)** — audience fatigue and reach decline triggers for retention alerts
- **Stage 10 (Recommendation Engine)** — retention risks and fatigue signals drive retention recommendations
- **Stage 12 (Report Assembly)** — retention score and narrative appear in the weekly retention report section
