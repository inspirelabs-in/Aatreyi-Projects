# Skill: Outcome Tracking

## Purpose

Measure whether the recommendations the agent generated actually worked. Close the feedback loop between what the agent recommended and what happened to the channel as a result. Use that learning to make future recommendations more accurate.

Without outcome tracking, the agent is a one-way broadcaster of advice. With it, the agent becomes a system that improves over time — one that learns which strategies work for which channel types, which recommendations fail in certain contexts, and which evidence patterns are reliable predictors of success.

---

## When This Skill Runs

- **Baseline recording:** Immediately when a recommendation is generated (captures the "before" state)
- **Outcome measurement:** At the end of the measurement window defined in each recommendation (7–14 days after generation)
- **Learning update:** After each outcome is recorded (updates confidence calibration for future recommendations)
- **Weekly review:** Included in the weekly report (shows operator what last week's recommendations achieved)

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `recommendations` | Stage 10 | All generated recommendations with their success metrics and thresholds |
| `alerts` (actioned) | Stage 9 | Alerts the operator marked as actioned |
| Current metric values | Data collection | Fetched at outcome measurement time |
| `channel_profile` | Stage 2 | Used for grouping outcome patterns by channel type |

---

## Recommendation Lifecycle

Every recommendation passes through a defined lifecycle:

```
Generated
    ↓
Accepted       ← Operator acknowledged the recommendation
    ↓
Implemented    ← Operator marked it as implemented OR system detected matching behavior change
    ↓
In Measurement ← Measurement window is running; metrics being monitored
    ↓
Measured       ← Measurement window closed; outcome calculated
    ↓
Successful / Failed / Inconclusive
```

### State Definitions

**Generated:** The recommendation has been created and delivered to the operator. Baseline metrics are recorded at this point.

**Accepted:** The operator acknowledged the recommendation (tapped a confirmation button or replied positively). Not all recommendations require explicit acceptance.

**Implemented:** The operator indicated they took the recommended action, OR the system detects behavioral evidence consistent with implementation (e.g., a recommendation to increase video content is auto-detected as implemented if video post percentage increases within 3 days).

**In Measurement:** The measurement window (7–14 days as defined in the recommendation) is running. The system monitors the target metric daily.

**Measured:** The measurement window has closed. The outcome is calculated.

**Successful:** The target metric met or exceeded the success threshold defined in the recommendation within the measurement window.

**Failed:** The measurement window closed without the metric reaching the success threshold.

**Inconclusive:** An external event (a Telegram platform-wide reach change, a competitor spike drawing audience away, or a major external news event affecting the niche) makes it impossible to cleanly attribute the metric change to the recommendation.

---

## Baseline Metric Recording

When a recommendation is generated, the system records a snapshot of the target metric's current value. This is the "before" state.

For each recommendation, the following baseline snapshot is taken:

```
baseline:
  recommendation_id: string
  recorded_at: datetime
  target_metric: string                  # The metric this recommendation aims to improve
  current_value: float                   # Current value of the target metric
  7d_average: float                      # 7-day rolling average
  30d_average: float                     # 30-day rolling average
  trend_at_baseline: string              # Improving / Stable / Declining at time of recommendation
```

---

## Outcome Measurement

At the end of the measurement window, the system fetches the current value of the target metric and computes the outcome.

### Outcome Calculation

```
absolute_change = after_value - baseline_current_value
relative_change = (after_value - baseline_current_value) / baseline_current_value × 100
goal_achievement = after_value >= success_threshold
```

### Outcome Classification Rules

**Successful:**
- `after_value >= success_threshold`
- AND the trend at measurement time is Stable or Improving (not a temporary spike that has already reversed)

**Failed:**
- `after_value < success_threshold`
- AND no qualifying external confound is detected

**Inconclusive:**
Any of the following:
- A Telegram platform-wide metric change affected all channels in the category during the measurement window (detected by checking if competitor metrics changed in the same direction simultaneously)
- The operator did not implement the recommendation (status never reached Implemented)
- A major niche-specific external event occurred during the measurement window (e.g., a major product launch flooded the category with competing content)

---

## Learning System

The primary value of outcome tracking is not the individual outcome measurement — it is the accumulation of patterns across many recommendations over time that makes future recommendations better.

### What the System Learns

**1. Recommendation Category Success Rates**
For each recommendation category (Content, Growth, Retention, Engagement, Competitor, Opportunity), the system tracks what percentage of recommendations in that category succeeded, for which channel types.

This produces a prior probability for each recommendation category: "content mix change recommendations succeed 72% of the time for Deals & Affiliate channels in the Medium tier." This prior updates the confidence score for future recommendations of the same type.

**2. Evidence Pattern Reliability**
Some evidence patterns are strong predictors of recommendation success; others are not. The system tracks which specific evidence patterns (e.g., "underutilized category with normalized score > 1.2") predict successful outcomes and which do not.

Over time, evidence patterns with low predictive reliability are weighted down in the recommendation scoring, and patterns with high reliability are weighted up.

**3. Channel-Specific Learning**
The system maintains a channel-level learning record — what has worked for this specific channel, what has failed. A recommendation that failed 3 times for the same channel is not regenerated unless the underlying conditions have changed significantly.

**4. Timing and Sequencing Effects**
Sometimes a recommendation fails not because the underlying insight is wrong, but because of sequencing — trying to increase video content while the channel is in an active audience fatigue state, for example, will not produce the expected results. The system learns these interaction effects and adjusts the sequencing of recommendations.

### Confidence Score Calibration

The confidence score on new recommendations is adjusted by multiplying the base evidence confidence by the category success rate:

```
calibrated_confidence = base_evidence_confidence × category_success_rate_for_this_channel_type
```

A recommendation type with strong evidence but a poor track record for this channel type will surface with lower confidence than one with moderate evidence but a strong track record. The operator sees the adjusted confidence score, not the raw evidence score.

---

## Outputs

```
outcome_history:
  recommendations_generated_total: int
  recommendations_measured: int
  
  outcomes:
    - recommendation_id: string
      title: string
      category: string
      generated_at: datetime
      status: string                     # Full lifecycle status
      baseline_value: float
      measured_value: float
      absolute_change: float
      relative_change: float
      success_threshold: float
      outcome: string                    # Successful / Failed / Inconclusive
      outcome_notes: string              # Any relevant context
  
  success_rates:
    overall: float                       # % successful out of measured
    by_category:
      content: float
      growth: float
      retention: float
      engagement: float
      competitor: float
      opportunity: float
  
  learning_adjustments:                  # What the system has updated based on outcomes
    - insight: string
      applied_to: string                 # Which future recommendation types this affects
  
  weekly_outcome_summary: string         # Plain-language summary for the weekly report
```

---

## Weekly Outcome Review (for report)

The weekly report includes a structured outcome review section:

**Last Week's Recommendation Results:**
For each recommendation from last week that has completed its measurement window:
- What was recommended
- What the operator did (Implemented / Not Implemented)
- What happened to the target metric
- Whether the recommendation is marked Successful, Failed, or Inconclusive
- One-line insight derived from the outcome

**Recommendation Track Record (rolling 30 days):**
Overall success rate and success rate by category. This gives the operator growing confidence in the recommendations over time — or surfaces patterns that the agent should flag if a category is consistently producing failed recommendations (which would prompt the agent to re-examine the underlying evidence quality for that category).

---

## Downstream Dependencies

`outcome_history` is used by:

- **Stage 10 (Recommendation Engine)** — calibrated confidence scores, category success rates, channel-specific learning adjustments
- **Stage 12 (Report Assembly)** — weekly outcome review section
