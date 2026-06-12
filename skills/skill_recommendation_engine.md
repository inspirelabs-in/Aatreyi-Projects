# Skill: Recommendation Engine

## Purpose

Convert all analysis outputs into a prioritized, evidence-backed action plan. Every recommendation must be specific, actionable, and tied to measurable outcomes. The recommendation engine does not produce suggestions — it produces instructions with reasoning.

The measure of a good recommendation is not that it sounds reasonable, but that when acted upon, it produces a measurable improvement in the target metric.

---

## When This Skill Runs

- **Daily plan generation:** Every morning at 6:00 AM (operator's time zone)
- **Weekly recommendations:** Every Monday with the weekly report
- **On-demand:** When the operator requests a focused recommendation

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 | Channel type, goal, content style |
| `audience_profile` | Stage 3 | Activity windows, engagement behavior, content preferences |
| `content_intelligence` | Stage 4 | Category scores, underutilized opportunities, oversaturation flags, optimal posting windows |
| `competitor_intelligence` | Stage 5 | Competitive gaps, fastest-growing competitor's strategy |
| `benchmark_results` | Stage 6 | Gap scores for all key metrics, competitive position per metric |
| `growth_analysis` | Stage 7 | Growth score, growth drivers, bottlenecks, opportunities |
| `retention_analysis` | Stage 8 | Retention score, fatigue status, retention risks |
| `alerts` | Stage 9 | Active Critical and Warning alerts |
| `outcome_history` | Stage 11 | Historical recommendation success rates by category |

---

## Recommendation Categories

Recommendations are drawn from six source categories:

| Category | Derived From | Example |
|---|---|---|
| Content | Underutilized categories, oversaturation flags, format gaps | "Increase video review posts from 2% to 15% of content mix" |
| Growth | Growth bottlenecks, growth opportunities, competitor gaps | "Post earphone deals between 8–10 PM — your afternoon posts get 40% fewer forwards" |
| Retention | Retention risks, fatigue signals, ERR decline | "Reduce posting frequency from 8/day to 3/day for 7 days to break the fatigue cycle" |
| Engagement | Audience profile gaps, ERR trends, poll/interaction deficit | "Run a weekly 'Deal of the Week' poll — 4 of 5 competitors do this; it averages 3x their normal engagement" |
| Competitor | Competitive gaps, competitor strategy changes | "Introduce short video product reviews — Competitor A grew 8% in the month they started this format" |
| Opportunity | Trending topics, content gap alerts | "Post about [trending topic] — it's currently performing above average across 3 competitors" |

---

## Daily Plan Generation

The daily plan is a short, specific, immediately actionable brief. It is designed to be read in under 90 seconds and acted on the same day.

### Daily Plan Structure

**1. Today's Post Count and Timing**
Based on: audience peak activity windows, current retention health (if fatigue is active, reduce frequency), and the day-of-week pattern from content intelligence.

Output format: "Post 2 times today. Best windows: 8:00–9:00 AM and 9:00–10:00 PM."

**2. Today's Content Focus**
The specific category or topic to prioritize today. Selected based on: the highest-scoring underutilized category (if applicable), the content type that performed best in the last 7 days, or the content type recommended by current growth analysis.

Output format: "Focus on [Category] today. It is your second-most-posted category but your highest-engagement category — you posted none in the last 3 days."

**3. Engagement Action (if applicable)**
Whether to include an interactive element today (poll, question, reaction prompt). Triggered when ERR has been declining for 3+ days or when the audience profile indicates interactive content is underused.

Output format: "Include a reaction poll today — your ERR has declined 3 days in a row. A poll will drive interaction without requiring new content creation."

**4. Active Alert Action (if applicable)**
If a Critical or Warning alert is active, the daily plan includes the specific action to address it.

Output format: "Critical: Your reach dropped 24% yesterday. Reduce post count to 1 today and make it your highest-quality content type (earphone deals based on your history)."

**5. Competitor Note (if applicable)**
If a competitor alert fired in the last 24 hours, a one-line note about what to watch or respond to.

---

## Weekly Recommendation Generation

Weekly recommendations are deeper, more strategic, and oriented toward 7–30 day improvement arcs. Each week produces exactly 5 prioritized recommendations.

### Recommendation Prioritization Logic

Candidate recommendations are generated from all six source categories. They are then scored and ranked on three dimensions:

**Dimension 1 — Expected Impact (50% of priority score)**
Estimated improvement to a key metric if the recommendation is implemented. Based on:
- Benchmark gap size: the larger the gap to peer average for the relevant metric, the higher the expected impact
- Competitor evidence: if competitors who use this strategy have measurably better metrics, the evidence is strong
- Content performance correlation: if the channel's own historical data shows that similar behavior produced better results, the evidence is strong

**Dimension 2 — Implementation Effort (30% of priority score)**
How difficult is this recommendation to act on? Scored from 1 (easy: change a posting time) to 5 (hard: produce weekly video content that requires new production capabilities). Lower effort gets higher priority, all else equal.

**Dimension 3 — Confidence (20% of priority score)**
How confident is the agent in this recommendation, based on:
- Evidence quality (competitor data + own channel data = high confidence; one source only = medium)
- Outcome history: if the same type of recommendation has succeeded for this channel in the past, confidence is higher; if it has failed, confidence is lower

### Recommendation Structure

Each of the 5 weekly recommendations contains:

```
recommendation:
  rank: int                          # 1–5 priority ranking
  title: string                      # Specific, action-oriented title (not vague)
  category: string                   # Content / Growth / Retention / Engagement / Competitor / Opportunity
  
  priority_score: float              # Composite score used for ranking
  confidence: string                 # High / Medium / Low
  expected_impact: string            # Specific metric + estimated change (e.g., "+15–25% reach %")
  
  evidence:
    - source: string                 # "Own channel data" / "Competitor A" / "Benchmark data"
      data_point: string             # Specific fact supporting the recommendation
  
  action_steps: [string]             # Numbered step-by-step instructions
  
  timeline: string                   # "Start today" / "Implement this week" / "Test over 14 days"
  
  success_metric: string             # Specific metric to track (e.g., "ERR should increase from 4.2% to 5.5%+ within 14 days")
  success_threshold: float           # The value the metric needs to reach to call this successful
  measurement_window_days: int       # How long to wait before measuring outcome (typically 7–14)
```

### Example of a Fully Structured Recommendation

```
rank: 1
title: "Shift 30% of charger deal posts to earphone and smartwatch deals"
category: Content

confidence: High
expected_impact: "+20–35% average post engagement rate within 14 days"

evidence:
  - source: "Own channel data"
    data_point: "Earphone deal posts average 1.8x normalized engagement score; charger deals average 0.6x"
  - source: "Own channel data"
    data_point: "Charger deals represent 38% of posts but only 14% of total engagement"
  - source: "Benchmark data"
    data_point: "Top-performing channels in Mobile Accessories (India) allocate under 10% of posts to charger content"

action_steps:
  - "For the next 14 days, post no more than 1 charger deal per day (down from current average of 3)"
  - "Replace removed charger posts with earphone deals (2 per day) and smartwatch deals (1 per day)"
  - "Use the best-performing earphone post from the last 30 days as a format template"
  - "After 7 days, check average post engagement — if it has not improved, check if the earphone posts were published in the 8–10 PM window (your best-performing window)"

timeline: "Start today"
success_metric: "Average normalized engagement score"
success_threshold: 1.1
measurement_window_days: 14
```

---

## On-Demand Recommendation Handling

When the operator sends a query requesting a specific recommendation, the engine identifies the relevant intent and runs a targeted analysis:

| Query Intent | Analysis Run | Output |
|---|---|---|
| "What should I post tomorrow?" | Audience activity + content scores + current alerts | Next-day post plan with specific category, timing, and format |
| "How do I improve my reach?" | Reach trend + benchmark gap + competitor format comparison | 3 specific reach improvement actions with evidence |
| "Why did my engagement drop?" | Content score trends + posting pattern + ERR analysis | Causal diagnosis + 2 corrective actions |
| "What content performs best for me?" | Content intelligence category ranking | Top 3 categories with scores, optimal format per category |

---

## Downstream Dependencies

`recommendations` output is used by:

- **Stage 11 (Outcome Tracking)** — each recommendation's baseline metrics are recorded for outcome measurement
- **Stage 12 (Report Assembly)** — daily plan and weekly top-5 recommendations are included in all reports
