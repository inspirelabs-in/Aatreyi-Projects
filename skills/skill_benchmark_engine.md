# Skill: Benchmark Engine

## Purpose

Place the channel's performance in context. Raw metrics are meaningless without comparison — a 5% monthly growth rate is either excellent or terrible depending on what similar channels are achieving. The Benchmark Engine determines whether each of the channel's key metrics is strong, average, or weak relative to the market it operates in.

---

## When This Skill Runs

- Every weekly pipeline run
- On-demand when the operator requests a performance comparison

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 | Category, subcategory, geography, maturity, subscriber count |
| `content_intelligence` | Stage 4 | Engagement rates, reach %, posting frequency, format distribution |
| `growth_data` | Data collection | Subscriber growth time series |
| `retention_data` | Data collection | Reach % trend, ERR trend |
| `competitor_intelligence` | Stage 5 | Enriched data for 5 tracked competitors |
| TGStat category data | External | Category-level aggregate statistics |

---

## Benchmark Cohort Construction

A channel's benchmark cohort is the set of channels against which it is compared. The cohort is constructed using five criteria drawn from the channel profile:

| Dimension | Value Used |
|---|---|
| Category | Primary category (e.g., Deals & Affiliate) |
| Subcategory | Subcategory (e.g., Mobile Accessories) — narrows the peer set |
| Geography | Geographic focus (e.g., National — India) |
| Subscriber Tier | Tier based on subscriber count (see below) |
| Channel Maturity | Maturity stage (New / Growing / Established / Mature) |

### Subscriber Tiers

| Tier | Subscriber Range |
|---|---|
| Micro | Under 10,000 |
| Small | 10,000–50,000 |
| Medium | 50,000–200,000 |
| Large | 200,000–1,000,000 |
| Very Large | Over 1,000,000 |

The cohort is narrowed progressively: the full cohort uses all five dimensions; if this returns fewer than 20 channels from TGStat data, the subcategory filter is dropped; if still under 20, the geography filter is dropped; if still under 20, the maturity filter is dropped.

---

## Three Benchmark Types

### Type 1 — Industry Benchmark

The full category average across all channels in the same primary category, regardless of size, geography, or maturity. This is the broadest reference point — it answers "how does this channel compare to the entire category?"

### Type 2 — Peer Benchmark

The average computed from the 5 tracked competitors plus any additional channels that match the full cohort definition (category + subcategory + geography + subscriber tier + maturity). This is the most meaningful benchmark for strategic comparison — it answers "how does this channel compare to channels that are directly competing for the same audience?"

The 5 tracked competitors are always included in the peer set. If TGStat provides additional category-matching channels, they supplement the peer set up to a maximum of 20 channels.

### Type 3 — Top Performer Benchmark

The metrics of the top 10% of channels in the full cohort (all five dimensions). This is the aspirational benchmark — it answers "what does best-in-class look like for this channel type, and how far away is this channel from that?"

---

## Metrics Benchmarked

For each of the three benchmark types, the engine computes a percentile rank for the following metrics:

### Growth Metrics
| Metric | How Computed |
|---|---|
| Monthly Subscriber Growth Rate | (subscribers gained in last 30 days) / (subscribers at start of period) × 100 |
| 7-Day Growth Rate | Same formula, 7-day window |
| Growth Trend Direction | Whether growth rate is accelerating, stable, or decelerating vs. the prior 30-day period |

### Reach Metrics
| Metric | How Computed |
|---|---|
| Average Reach % | Mean of (post views / subscribers) across last 30 posts |
| Reach Trend | Direction of reach % over last 4 weeks |
| Peak Post Reach % | 90th percentile post views / subscribers (best-case reach) |

### Engagement Metrics
| Metric | How Computed |
|---|---|
| Engagement Rate (ER) | (total reactions + forwards) / subscriber count |
| Engagement Rate by Reach (ERR) | (total reactions + forwards) / total views |
| Reaction Rate | Total reactions / total views |
| Forward Rate | Total forwards / total views |

### Content Metrics
| Metric | How Computed |
|---|---|
| Video Content Usage % | Posts using video / total posts |
| Poll Usage Frequency | Number of poll posts per week |
| Posting Frequency | Average posts per day |
| Content Diversity Score | Number of distinct content categories with at least 5% share of posts |

---

## Normalization

Before computing benchmarks, all engagement metrics are normalized to remove size distortion. A channel with 200,000 subscribers will have higher raw view counts than a channel with 20,000 subscribers — but their normalized engagement rates may be comparable.

All metrics are computed as rates or percentages (not absolutes) before comparison. The subscriber count is used only for tier classification, not in the metric computation itself.

---

## Percentile Calculation

For each metric, the engine places the user's channel in the distribution of the cohort:

- **90th percentile or above** — Top performer
- **75th–90th percentile** — Strong performer
- **50th–75th percentile** — Above average
- **25th–50th percentile** — Below average
- **10th–25th percentile** — Weak performer
- **Below 10th percentile** — Lagging significantly

---

## Gap Score

For each metric, a gap score is computed against the peer benchmark:

```
gap_score = user_channel_metric_value - peer_benchmark_average
```

A positive gap score means the user's channel is above the peer average for that metric. A negative gap score means it is below.

Gap scores are used by the Growth Analysis, Recommendation Engine, and Report Assembly stages to prioritize which gaps are most important to close.

---

## Competitive Position Classification

For each benchmarked metric, the channel receives a competitive position label:

| Label | Criteria |
|---|---|
| Leading | Above 75th percentile vs. peer benchmark |
| On-Par | Between 40th and 75th percentile vs. peer benchmark |
| Lagging | Below 40th percentile vs. peer benchmark |
| Critical | Below 20th percentile vs. peer benchmark |

---

## Outputs

```
benchmark_results:
  cohort_definition:
    category: string
    subcategory: string
    geography: string
    subscriber_tier: string
    maturity: string
    cohort_size: int
    dimensions_used: [string]          # Which dimensions were used after fallback
  
  metrics:
    - metric_name: string
      user_value: float
      industry_percentile: int
      peer_percentile: int
      top_performer_value: float
      gap_to_peer_average: float
      gap_to_top_performer: float
      competitive_position: string     # Leading / On-Par / Lagging / Critical
  
  overall_competitive_position: string  # Composite of all metric positions
  strongest_metric: string              # Metric where channel leads the most
  weakest_metric: string                # Metric with largest negative gap
  
  benchmark_data_freshness: datetime
```

---

## Downstream Dependencies

`benchmark_results` is used by:

- **Stage 7 (Growth Analysis)** — growth rate context and gap prioritization
- **Stage 8 (Retention Analysis)** — reach and engagement benchmark context
- **Stage 10 (Recommendation Engine)** — gap scores determine which improvements have the most competitive leverage
- **Stage 12 (Report Assembly)** — percentile positions are displayed in the weekly report's benchmark section
