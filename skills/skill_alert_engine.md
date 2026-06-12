# Skill: Alert Engine

## Purpose

Monitor the channel's metrics continuously and dispatch an alert the moment something important happens — a drop, a spike, a risk, or an opportunity — so the operator can act immediately rather than discovering the issue days later in a weekly report.

Alerts are the agent's real-time nervous system. Every alert must be specific enough to act on immediately, without requiring additional research from the operator.

---

## When This Skill Runs

- Monitoring loop: every 30 minutes, independent of the main pipeline
- Alert generation: triggered when a threshold is breached
- Alert enrichment: runs after the next scheduled analysis pipeline to add context to previously dispatched alerts

---

## Inputs for Monitoring Loop

| Input | Source | Refresh Rate |
|---|---|---|
| `subscriber_count` | Telegram API | Every 6 hours |
| `latest_post_engagement` | Telegram API | Every 6 hours |
| `reach_percentage_rolling` | Computed from engagement data | Updated with each data refresh |
| `growth_analysis.growth_trend` | Stage 7 output | Updated on daily analysis run |
| `retention_analysis.audience_fatigue` | Stage 8 output | Updated on daily analysis run |
| `competitor_intelligence.change_flags` | Stage 5 output | Updated on 24-hour competitor refresh |
| `content_intelligence.score_trends` | Stage 4 output | Updated on daily analysis run |

---

## Alert Taxonomy

### Category 1 — Growth Alerts

**Growth Drop Alert**
- Trigger: 7-day growth rate falls below 50% of the channel's 30-day average growth rate
- Severity: Warning
- Example: Channel had been growing at 2% per week for 30 days; growth drops to 0.8% this week
- Alert content: Current growth rate, 30-day average, percentage drop, likely cause from growth analysis, one recommended action

**Growth Spike Alert**
- Trigger: Single-day subscriber gain exceeds 300% of the channel's average daily gain
- Severity: Opportunity
- Example: Channel gains 2,000 subscribers in a day when the average is 400
- Alert content: Gain amount vs. average, which posts were published in the preceding 24 hours, recommendation to capitalize immediately

---

### Category 2 — Reach Alerts

**Reach Drop Alert**
- Trigger: Average reach % over the last 3 posts is more than 20% below the channel's 7-day rolling average reach %
- Severity: Warning (drops to Critical if the decline has been sustained for 5+ consecutive days)
- Example: Channel's 7-day average reach is 18%; last 3 posts averaged 12% reach
- Alert content: Current vs. average reach %, duration of decline, probable cause, recommended action

**Reach Spike Alert**
- Trigger: A single post reaches more than 3x the channel's average views within 6 hours of posting
- Severity: Opportunity
- Alert content: The post that spiked, what category it belongs to, performance vs. average, recommendation to follow up with similar content within 24 hours

---

### Category 3 — Engagement Alerts

**ER Drop Alert**
- Trigger: Engagement rate over the last 7 posts is below 60% of the channel's 30-day average ER
- Severity: Warning
- Alert content: Current vs. average ER, which content categories are underperforming, pattern analysis

**ERR Drop Alert**
- Trigger: Engagement rate by reach (ERR) over the last 7 posts is below 60% of the 30-day average ERR
- Severity: Warning
- Significance: ERR drop independent of reach drop suggests content quality is declining, not just distribution

---

### Category 4 — Retention Alerts

**Audience Fatigue Alert**
- Trigger: Retention analysis fatigue status transitions to `Emerging` or `Active`
- Severity: Warning for Emerging; Critical for Active
- Alert content: Which fatigue signals are present, the specific content pattern driving fatigue, a specific intervention (e.g., "reduce posting frequency from 6/day to 3/day for the next 7 days")

**Retention Risk Alert**
- Trigger: Retention score drops below 40
- Severity: Critical
- Alert content: Retention score and component breakdown, the dominant risk factor, immediate action required

---

### Category 5 — Competitor Alerts

**Competitor Growth Spike Alert**
- Trigger: A tracked competitor's 7-day growth rate exceeds 2x their 30-day average growth rate
- Severity: Info (escalates to Warning if the same competitor has spiked 3 weeks in a row)
- Alert content: Which competitor, their growth rate this week vs. average, what content they published during their spike, what the user's channel can learn or respond with

**Competitor Strategy Change Alert**
- Trigger: A tracked competitor's content type distribution shifts by more than 15 percentage points in any single format over 30 days (e.g., video goes from 5% to 22%)
- Severity: Info
- Alert content: Which competitor, what changed, when it started, whether their engagement improved following the change, strategic implication for the user's channel

---

### Category 6 — Opportunity Alerts

**Trending Topic Alert**
- Trigger: A content topic or product category is performing above average across 3 or more tracked competitor channels simultaneously
- Severity: Opportunity
- Alert content: The trending topic, how many competitors are covering it, their average performance uplift, whether the user's channel has posted on this topic

**Content Gap Alert**
- Trigger: An underutilized content category (flagged in content intelligence) has shown above-average engagement on its most recent appearances, OR a competitor is using a format that the user's channel has never used and it is associated with their growth spike
- Severity: Opportunity
- Alert content: The specific gap, the evidence supporting it, a concrete example of what content to create

**Posting Gap Alert**
- Trigger: No post has been published for more than 36 hours when the channel's typical posting frequency is daily or higher
- Severity: Info
- Alert content: Hours since last post, typical posting frequency, reminder to post to maintain audience habit

---

## Alert Severity Framework

| Severity | Meaning | Delivery |
|---|---|---|
| Critical | Active problem requiring immediate action within 24 hours | Telegram message, highlighted in daily plan |
| Warning | Developing problem that needs attention within 3–7 days | Telegram message, included in next daily plan |
| Opportunity | Positive signal or gap to act on within 7 days | Telegram message |
| Info | Informational update — no immediate action required | Included in daily digest, not a separate push |

---

## Alert Structure

Every dispatched alert contains the following fields:

```
alert:
  id: string                           # Unique alert ID for tracking
  type: string                         # Alert type name
  severity: string                     # Critical / Warning / Opportunity / Info
  triggered_at: datetime
  
  headline: string                     # One sentence: what happened
  metric_snapshot:
    metric_name: string
    current_value: float
    reference_value: float             # Average or benchmark it's being compared to
    delta: float                       # Absolute and percentage difference
  
  probable_cause: string               # Specific data-backed explanation
  recommended_action: string           # Specific action to take — not generic advice
  action_timeframe: string             # "within 24 hours" / "this week" / etc.
  
  supporting_evidence: [string]        # 2–3 data points supporting the diagnosis
  related_posts: [string]              # Post IDs relevant to the alert (if applicable)
```

---

## Alert Deduplication and Throttling

To prevent alert fatigue (the operator ignoring alerts because they receive too many):

- The same alert type cannot fire more than once per 24-hour window for the same metric
- If a Critical alert is active, related Warning alerts for the same metric are suppressed until the Critical is resolved
- Opportunity alerts are batched into a single daily digest if more than 2 fire in a 6-hour window
- Resolved alerts (metric has recovered above threshold) are automatically closed with a resolution note

---

## Alert Resolution Tracking

Each alert has a lifecycle:
- **Active** — threshold is breached; alert has been dispatched
- **Monitoring** — metric is still below threshold but trend is improving
- **Resolved** — metric has recovered above threshold
- **Acknowledged** — operator has marked the alert as seen (reduces repeat notifications)
- **Actioned** — operator has indicated they have taken the recommended action (feeds outcome tracking)

Alerts that are Actioned feed into the Outcome Tracking stage as recommendation-equivalent events, allowing the system to measure whether the recommended action resolved the problem.

---

## Downstream Dependencies

`alerts` output is used by:

- **Stage 10 (Recommendation Engine)** — active Critical and Warning alerts are prioritized in daily plan
- **Stage 11 (Outcome Tracking)** — actioned alerts are tracked as recommendation-equivalent events
- **Stage 12 (Report Assembly)** — alert log included in weekly report; active alerts highlighted in daily plan
