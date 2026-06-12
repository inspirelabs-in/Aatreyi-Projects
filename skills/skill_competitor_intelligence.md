# Skill: Competitor Intelligence

## Purpose

Identify the channels operating in the same niche, collect their performance and content data, analyze what is driving their growth, and produce a competitive intelligence picture that allows the operator to understand where they stand relative to the market and what opportunities the competitive landscape reveals.

---

## When This Skill Runs

- **Competitor discovery:** Once per week (to detect new entrants)
- **Competitor data enrichment:** Every 24 hours (to track changes)
- **Competitor analysis:** Every daily and weekly pipeline run (using the most recent enriched data)

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel_profile` | Stage 2 | Category, subcategory, geography, subscriber count |
| `content_intelligence` | Stage 4 | Top-performing categories (used for keyword extraction) |
| `operator_competitor_list` | User setup | Optional list of known competitor @usernames |
| TGStat API | External | Competitor search and stats |
| Telemetr.io API | External | Secondary competitor search and audience data |
| Telegram MTProto Search | Telegram API | Direct channel search for emerging competitors |

---

## Part 1 — Competitor Discovery

### Step 1: Keyword Extraction

The agent derives 3–5 search keywords from:
1. The channel's subcategory label (most specific signal)
2. The top 2 performing content categories from content intelligence
3. Recurring high-frequency nouns in the post corpus (product names, topics, brand names)
4. The geographic focus (appended to narrow results where relevant)

**Example — Mobile Accessories Deals Channel (India):**
Keywords derived: `mobile accessories deals`, `earphones India`, `tech deals telegram`, `gadget offers`

**Example — UPSC Preparation Channel:**
Keywords derived: `UPSC preparation`, `current affairs daily`, `IAS coaching`, `competitive exam India`

### Step 2: Multi-Source Parallel Search

The extracted keywords are submitted simultaneously to three sources:

**TGStat:**
- Endpoint: category search + keyword search
- Filters applied: last post within 14 days, language match, subscriber count between 30% and 1000% of user's channel size
- Returns: channel list with subscriber counts, 30-day growth rate, engagement rate

**Telemetr.io:**
- Endpoint: channel search by keyword
- Additional filter: audience overlap score above 0.3 (ensures the candidate's audience genuinely overlaps with the user's niche)
- Returns: channel list with subscriber trends, ad activity level, estimated reach

**Telegram MTProto Search:**
- Direct channel search using each keyword phrase
- Filters: subscriber count above 1,000, has posted within 7 days
- Returns: channel list from Telegram's own index — catches channels not yet in external databases

Results from all three sources are merged. Duplicate channels (same canonical ID appearing from multiple sources) are deduplicated and given a multi-source match bonus in ranking.

### Step 3: Scoring and Selection

Each candidate channel is scored on five factors:

| Factor | Weight | How Scored |
|---|---|---|
| Category match | 35% | Claude-assessed overlap between candidate's content and user channel's content taxonomy |
| Size proximity | 25% | Closer to user's subscriber count = higher score; extreme size difference = penalty |
| Recent growth rate | 20% | Higher recent growth rate = higher score (more relevant for benchmarking) |
| Posting activity | 10% | Channels posting at least 3x per week score higher |
| Multi-source presence | 10% | Appearing in 2 or 3 sources scores higher than appearing in only 1 |

The top 5 scoring candidates become the tracked competitor set. If the operator specified known competitors during setup, those are always included and occupy slots in the top 5 regardless of their score.

If fewer than 3 viable competitors are found after filtering, the geographic filter is broadened (e.g., from national to regional), and the size filter is expanded (from 30%–1000% to 10%–5000%). If still fewer than 3, the category is broadened to the parent category and the process repeats.

---

## Part 2 — Competitor Data Enrichment

For each of the 5 tracked competitors, the following data is collected every 24 hours:

### Subscriber Data
- Current subscriber count
- Subscriber delta since last 24h snapshot
- 7-day subscriber delta
- 30-day subscriber delta
- Calculated 30-day growth rate percentage

### Engagement Data
- Average views per post (last 30 posts)
- Average forwards per post (last 30 posts)
- Average reactions per post (last 30 posts)
- Calculated engagement rate (reactions + forwards / subscriber count)
- Calculated engagement rate by reach (reactions + forwards / views)

### Content Data
- Content type distribution: percentage of posts that are text-only, text + photo, text + video, poll, link-only (last 30 posts)
- Post frequency: average posts per day over the last 30 days
- Posting time distribution: which hours of the day they post most frequently
- Top 3 performing posts from the last 7 days (by views and forwards)

### Change Detection
On each 24-hour refresh, the system compares new values to the previous snapshot and flags significant changes:

| Change Type | Trigger Threshold |
|---|---|
| Growth spike | 7-day growth rate exceeds 150% of their 30-day average |
| Engagement jump | Average engagement rate increases by 30%+ week-over-week |
| Format shift | A content type increases or decreases by more than 15 percentage points |
| Frequency change | Posts per day changes by more than 50% week-over-week |

Flagged changes are passed to the Alert Engine as competitor strategy change events.

---

## Part 3 — Competitor Intelligence Analysis

With enriched data collected, Claude analyzes the competitive landscape to answer four questions:

### Question 1: What strategies are working for competitors that we are not using?

The agent identifies content formats, posting behaviors, and engagement tactics that high-performing competitors use but the user's channel does not. These become competitive gap opportunities.

Examples of gaps:
- Competitor A uses video content for 25% of posts; user's channel uses video for 3% — and competitors using video have 40% higher engagement rates
- Competitor B runs a weekly poll that consistently generates 3x their average engagement; user's channel has never run a poll
- Competitors post at 8–10 PM consistently; user's channel posts throughout the day — but evening posts across competitors outperform daytime posts

### Question 2: What is driving the fastest-growing competitor's growth?

The agent identifies the top-growing competitor by 30-day growth rate and analyzes what changed in their content or posting behavior during their growth period. This produces a replicable insight: here is what worked for the fastest grower, and here is why it likely worked.

### Question 3: Is the competitive landscape shifting?

Are multiple competitors simultaneously moving in a new direction? If 3 of 5 tracked competitors have increased video content in the last 30 days, that is a market-level shift worth surfacing as a strategic signal — not just a single competitor's experiment.

### Question 4: Where is the user's channel gaining or losing competitive ground?

For each key metric (growth rate, engagement rate, reach %), is the user's channel moving closer to or further from the competitor average? Gaining ground = positive competitive momentum. Losing ground = competitive deterioration.

---

## Outputs

```
competitor_intelligence:
  tracked_competitors:
    - channel_id: string
      title: string
      subscribers: int
      growth_rate_30d: float
      avg_views: int
      engagement_rate: float
      content_distribution:
        text: float
        photo: float
        video: float
        poll: float
        link: float
      posts_per_day: float
      top_posts_last_7d: [object]
      change_flags: [string]         # List of detected change events
  
  competitive_gaps: [object]
    - gap_type: string               # Format / Frequency / Timing / Engagement tactic
      description: string
      evidence: string               # Specific competitor data supporting this gap
      impact_estimate: string        # High / Medium / Low
  
  fastest_growing_competitor: string
  fastest_growth_driver: string      # What is driving their growth
  
  market_trends: [string]            # Shifts observed across 3+ competitors simultaneously
  
  competitive_momentum: string       # Gaining / Holding / Losing (vs competitor average)
  
  discovery_last_run: datetime
  next_discovery_run: datetime
```

---

## Downstream Dependencies

`competitor_intelligence` is used by:

- **Stage 6 (Benchmark Engine)** — competitor dataset is the basis for peer and top-performer benchmarks
- **Stage 7 (Growth Analysis)** — competitive gaps feed into growth opportunity identification
- **Stage 9 (Alert Engine)** — competitor change flags trigger competitor alerts
- **Stage 10 (Recommendation Engine)** — competitive gaps are a primary source of growth and content recommendations
