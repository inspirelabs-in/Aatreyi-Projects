# Skill: Content Intelligence

## Purpose

Understand what the channel is posting, how each type of content performs, and what the data implies about what to post more of, less of, and differently. This skill converts raw post history into a structured, scored content intelligence map that drives recommendations.

---

## When This Skill Runs

- Every daily pipeline run (new posts are scored as they arrive)
- Every weekly pipeline run (full re-analysis over the rolling 90-day window)

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 output | Category, subcategory, content style |
| `audience_profile` | Stage 3 output | Engagement behavior type, content preferences |
| `posts` | Data collection | Full post history — text, media type, links, timestamps |
| `engagement_data` | Data collection | Per-post views, forwards, reactions by type, reply counts |

---

## Step 1 — Content Taxonomy Construction

The first task is to build the channel's specific content taxonomy. The agent does not apply a generic taxonomy to all channels. It derives the taxonomy from what this channel actually posts.

### How the Taxonomy is Built

The agent reads all post content and groups posts by shared topic, format, and intent. Grouping is done by identifying recurring patterns: repeated product categories, recurring content formats, consistent post structures, and topical themes.

For a mobile accessories deals channel, the taxonomy might be:
- Earphone Deals
- Power Bank Deals
- Smartwatch Deals
- Flash Sale Alerts
- Product Reviews
- Comparison Posts
- Giveaway / Contest Posts

For a finance channel, the taxonomy might be:
- Daily Market Recap
- Stock Pick Analysis
- Breaking News Alert
- IPO Information
- Educational Explainer
- Portfolio Strategy
- Question / Poll

The taxonomy is channel-specific and updated on each weekly run to reflect any new content types that have emerged.

### Taxonomy Rules
- Every post belongs to exactly one primary category
- A post may have one secondary category tag if it clearly serves two purposes
- The taxonomy should have between 4 and 12 categories — fewer than 4 suggests the channel lacks diversity; more than 12 suggests over-granularity
- Categories must be meaningfully distinct — if two categories produce similar engagement patterns, they may be merged

---

## Step 2 — Post-Level Scoring

Each post receives a raw engagement score and a normalized engagement score.

### Raw Engagement Score

Computed from four signals weighted by their growth and retention relevance:

| Signal | Weight | Rationale |
|---|---|---|
| Forwards | 35% | Strongest growth signal — represents audience advocacy |
| Reactions | 30% | Emotional resonance signal — indicates content quality |
| Views | 20% | Reach signal — how many subscribers saw the post |
| Reply count | 10% | Community signal — generates conversation |
| Link click rate | 5% | Monetization signal — only counted when link data is available |

The link click rate weight increases to 20% (and the others proportionally reduced) for channels where the primary goal is monetization or affiliate revenue.

### Normalized Engagement Score

The raw score is normalized against the channel's own 30-day averages for each metric to produce a score that is comparable across posts regardless of when they were published (older posts may have higher view counts due to more time accumulating).

```
normalized_score = (
  (post_forwards / channel_30d_avg_forwards) × 0.35 +
  (post_reactions / channel_30d_avg_reactions) × 0.30 +
  (post_views / channel_30d_avg_views) × 0.20 +
  (post_replies / channel_30d_avg_replies) × 0.10 +
  (post_click_rate / channel_30d_avg_click_rate) × 0.05
)
```

Score interpretation:
- Above 1.5 — High performer: significantly above channel average
- 1.0–1.5 — Above average
- 0.5–1.0 — Below average
- Below 0.5 — Low performer: significantly below channel average

---

## Step 3 — Category-Level Analysis

Posts are grouped by their taxonomy category, and the following are computed for each category:

### Performance Metrics
- Average normalized score across all posts in the category
- Median normalized score (less sensitive to single outlier posts)
- Score trend: is performance improving, stable, or declining over the last 4 weeks?
- Best-performing post in the category (highest normalized score) — preserved as a reference example
- Worst-performing post in the category — preserved to illustrate what to avoid

### Format Analysis (within each category)
- Which media type (text-only, text + photo, text + video, poll, link-only) performs best within this category
- Optimal post length (character count range that produces above-average scores for this category)
- Optimal posting day and time within this category (cross-referenced with audience activity data)

### Frequency Analysis
- How often this category is currently posted (posts per week)
- Whether it is overused (posted more than the engagement rate justifies) or underused (posted less than the engagement rate suggests it could support)

**Underutilization detection:** A category is flagged as underutilized when its average normalized score is above 1.0 (above average performance) but it represents less than 10% of total posts. This is a direct growth opportunity — the audience responds well to this content but the channel is not producing enough of it.

**Oversaturation detection:** A category is flagged as oversaturated when it represents more than 40% of total posts but its score trend is declining over the last 4 weeks. This is an audience fatigue signal for that specific category.

---

## Step 4 — Cross-Category Insights

After individual category analysis, the agent looks for patterns across categories:

### Content Mix Health
Is the channel's content mix diverse enough? Channels where a single category accounts for more than 50% of all posts are at risk of audience fatigue in that category, even if the category currently performs well.

### Format Diversity
Is the channel over-relying on a single media type? Channels that post exclusively text or exclusively image content often underperform competitors that vary their formats. Flagged when one media type accounts for more than 70% of all posts.

### Recency Bias Check
Are recent posts (last 30 days) performing differently than the historical average? A significant drop in recent post scores — even if the historical average looks healthy — is an early signal worth flagging to the retention analysis stage.

### Posting Cadence vs. Performance
Does posting more on certain days of the week correlate with better or worse performance? Some channels have audiences that are more receptive on weekday mornings; others perform better on weekends. This cross-category timing analysis reveals structural patterns.

---

## Outputs

```
content_intelligence:
  taxonomy: [string]                     # List of content category names for this channel
  
  category_scores:
    - category: string
      avg_normalized_score: float
      score_trend: string                # Improving / Stable / Declining
      post_frequency_per_week: float
      utilization_status: string         # Optimal / Underutilized / Oversaturated
      best_performing_post_id: string
      worst_performing_post_id: string
      optimal_media_type: string
      optimal_post_length: string        # e.g., "100–200 characters"
      optimal_posting_window: string     # e.g., "Weekdays 8–10 PM"
  
  content_mix_health: string             # Healthy / Concentrated / Oversaturated
  format_diversity: string               # Diverse / Moderate / Low
  recency_signal: string                 # Improving / Stable / Declining
  top_performing_category: string
  worst_performing_category: string
  underutilized_opportunities: [string]  # Categories to increase
  oversaturated_categories: [string]     # Categories to reduce
  
  posting_cadence_insights:
    best_days: [string]
    best_hours: [int]
    current_posts_per_day: float
    recommended_posts_per_day: float
```

---

## Downstream Dependencies

`content_intelligence` is used by:

- **Stage 5 (Competitor Intelligence)** — keyword extraction for competitor search uses top-performing category labels
- **Stage 6 (Benchmark Engine)** — content format distribution is benchmarked against competitors
- **Stage 7 (Growth Analysis)** — growth driver identification uses content performance to correlate post types with subscriber events
- **Stage 8 (Retention Analysis)** — oversaturation flags and score trend data feed into fatigue detection
- **Stage 10 (Recommendation Engine)** — content recommendations are built directly from underutilized opportunities and oversaturation flags
