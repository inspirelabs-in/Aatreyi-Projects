# Skill: Growth Analysis

## Purpose

Answer the three questions every channel operator actually needs answered: why is the channel growing (or not), what is blocking further growth, and what specific actions would improve the growth rate. This skill converts subscriber data, content performance, and benchmark context into a causal growth narrative backed by evidence.

---

## When This Skill Runs

- Every daily pipeline run (to update the growth score and detect recent changes)
- Every weekly pipeline run (full retrospective growth analysis)

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 | Category, maturity, primary goal |
| `audience_profile` | Stage 3 | Engagement behavior, activity windows |
| `content_intelligence` | Stage 4 | Category scores, underutilized and oversaturated categories, cadence data |
| `competitor_intelligence` | Stage 5 | Competitor growth rates, competitive gaps |
| `benchmark_results` | Stage 6 | Growth rate percentile, gap scores |
| `subscriber_time_series` | Data collection | Daily subscriber count over last 180 days |
| `posts` + `engagement_data` | Data collection | Full post history with timestamps and engagement |

---

## Analysis Framework

### Framework Overview

Growth is not a single thing. It is the net result of multiple forces acting simultaneously:

- **Acquisition forces** — what brings new subscribers to the channel (shares, mentions, search, forwards)
- **Activation forces** — what converts a new visitor into a subscriber (first impression content quality)
- **Retention forces** — what keeps subscribers from leaving (ongoing content value)
- **Expansion forces** — what causes existing subscribers to actively promote the channel (advocacy behavior)

The growth analysis framework examines all four forces and produces a diagnosis of which are working, which are failing, and what the evidence is for each conclusion.

---

## Step 1 — Subscriber Time Series Analysis

The agent performs a structural analysis of the subscriber time series to identify:

**Growth Rate Calculation:**
- 7-day growth rate: subscribers gained in last 7 days / subscribers 7 days ago
- 30-day growth rate: same formula, 30-day window
- 90-day compound growth rate: annualized growth rate over the 90-day history

**Growth Trend Classification:**
The agent classifies the current growth trajectory as one of five states:

| State | Criteria |
|---|---|
| Accelerating | 30-day growth rate is 20%+ higher than the prior 30-day period |
| Stable Growth | Growth rate within ±20% of prior 30-day period |
| Decelerating | 30-day growth rate is 20%+ lower than the prior 30-day period |
| Plateau | Growth rate below 0.5% for 30+ consecutive days |
| Declining | Net negative growth (unsubscribes exceeding new subscribers) over 14+ days |

**Growth Event Detection:**
The agent scans the time series for significant spikes and drops — days where subscriber count changed by more than 3x the daily average. These events are flagged for correlation analysis in the next step.

---

## Step 2 — Growth-Content Correlation

For each detected growth spike or drop, the agent examines the posts published in the 48 hours preceding the event. This analysis identifies which content behaviors statistically coincide with growth acceleration and which precede growth deceleration.

### Growth Driver Identification

A content category or behavior is classified as a **growth driver** when:
- Posts from that category are disproportionately represented in the 48-hour windows before subscriber spikes
- The category's forward rate is above the channel average (forwards are the primary organic acquisition mechanism on Telegram)
- The pattern appears in at least 3 separate growth events (not a single coincidence)

### Growth Bottleneck Identification

A content category or behavior is classified as a **growth bottleneck** when:
- High-frequency posting of that category correlates with growth deceleration periods
- The category produces below-average forward rates (not being shared outside the channel)
- The behavior (e.g., over-posting, posting at low-engagement times) appears before multiple drop events

### Growth Opportunity Identification

Growth opportunities are not derived from the user's own data — they come from the gap between what the user's channel does and what successful competitors do. Specifically:

- Content categories that high-growth competitors use extensively but the user's channel uses rarely or never
- Posting behaviors (video, polls, timed series, giveaways) that correlate with growth spikes in competitor data but are absent from the user's channel
- Posting time windows where competitor posts outperform their averages but the user's channel rarely posts

Each growth opportunity is assigned an impact estimate based on the strength of the competitor evidence and the size of the gap.

---

## Step 3 — Growth Score Computation

The Growth Score is a composite 0–100 score representing the overall health of the channel's growth performance.

### Component Scores

| Component | Weight | How Scored |
|---|---|---|
| Current Growth Rate vs. Peer Benchmark | 35% | Peer percentile mapped to 0–100 |
| Growth Trend Direction | 25% | Accelerating = 100, Stable = 70, Decelerating = 40, Plateau = 20, Declining = 0 |
| Content-to-Growth Correlation Strength | 20% | How clearly identified growth drivers explain the growth pattern (0–100) |
| Posting Consistency | 10% | Standard deviation of daily post count over last 30 days, inverted (more consistent = higher score) |
| Forward Rate vs. Peer Benchmark | 10% | Forward rate peer percentile mapped to 0–100 |

### Score Interpretation

| Score Range | Label | What It Means |
|---|---|---|
| 80–100 | Strong | Channel is growing faster than most peers, with clear momentum |
| 60–79 | Healthy | Solid growth, some areas to optimize |
| 40–59 | Moderate | Growth is present but fragile or decelerating |
| 20–39 | Weak | Growth has stalled or is significantly below market average |
| 0–19 | Critical | Channel is declining or losing ground rapidly |

---

## Step 4 — Causal Narrative Construction

After quantitative analysis, the agent constructs a plain-language narrative explaining the growth situation. This narrative is what appears in the weekly report and daily plan — not raw numbers, but a clear explanation of what is happening and why.

The narrative is structured as three paragraphs:

1. **Current situation:** Where is growth right now, and what is the trend? (1–2 sentences)
2. **Why it is happening:** What specific evidence explains the current growth state? References specific content types, posting patterns, or competitive dynamics with their supporting data. (2–3 sentences)
3. **What to do:** What is the single most important action to take to improve growth? (1–2 sentences)

This narrative is specific. It does not say "post more content." It says "your earphone deal posts generate 4x more forwards than your charger deal posts, but you post charger deals 3x as often — shifting that balance is the highest-leverage action available."

---

## Outputs

```
growth_analysis:
  growth_score: int                    # 0–100
  growth_score_label: string           # Strong / Healthy / Moderate / Weak / Critical
  
  current_growth_rate_7d: float
  current_growth_rate_30d: float
  growth_trend: string                 # Accelerating / Stable / Decelerating / Plateau / Declining
  growth_rate_peer_percentile: int
  
  growth_drivers:
    - driver: string                   # Description of what is driving growth
      evidence: string                 # Specific data supporting this claim
      impact: string                   # High / Medium / Low
  
  growth_bottlenecks:
    - bottleneck: string
      evidence: string
      severity: string                 # High / Medium / Low
  
  growth_opportunities:
    - opportunity: string
      evidence: string                 # Competitor data or content gap evidence
      impact_estimate: string          # High / Medium / Low
  
  growth_narrative: string             # Plain-language explanation (3 paragraphs)
  
  key_actions:
    - action: string                   # Specific recommended action
      rationale: string
      priority: int
```

---

## Downstream Dependencies

`growth_analysis` is used by:

- **Stage 9 (Alert Engine)** — growth trend state triggers growth drop or growth spike alerts
- **Stage 10 (Recommendation Engine)** — growth drivers, bottlenecks, and opportunities are the primary inputs for growth recommendations
- **Stage 12 (Report Assembly)** — growth score and narrative appear in the weekly growth report section
