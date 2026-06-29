# Telegram Growth & Retention Agent — Rule-Based Metric Formulas

> All calculations below are deterministic, rule-based, and require no LLM.
> Variables reference the DB schema columns defined in `telegram_agent_db_schema.md`.

---

## 1. Channel DNA Metrics

### 1.1 Engagement Rate (ER)

Computed per post, then averaged over the analysis window.

```
ER_post = (reactions + forwards + replies) / views × 100

ER_channel = SUM(ER_post_i for i in window) / COUNT(posts in window)
```

**Rules:**
- Window = last 30 days (or all posts if channel < 30 days old)
- Minimum 5 posts required; otherwise mark `insufficient_data = true`
- Cap views at subscriber_count to avoid inflated reach from external shares

```
views_capped = MIN(views, subscriber_count)
ER_post      = (reactions + forwards + replies) / views_capped × 100
```

**Thresholds (benchmark):**

| ER Range | Label |
|---|---|
| < 1% | Poor |
| 1% – 3% | Average |
| 3% – 6% | Good |
| > 6% | Excellent |

---

### 1.2 Post Frequency

```
post_frequency_per_day = total_posts_in_period / days_in_period
```

**Example:** 21 posts over 7 days → `post_frequency_per_day = 3.0`

---

### 1.3 Best Post Hour

Group all posts by their UTC publish hour, compute average ER per hour bucket:

```
avg_er_by_hour[h] = SUM(ER_post_i  where hour(post_i.posted_at) == h)
                    ─────────────────────────────────────────────────
                    COUNT(posts where hour(posted_at) == h)

best_post_hour = argmax_h ( avg_er_by_hour[h] )   for h in 0..23
```

**Rule:** Only include hours with ≥ 3 posts to avoid single-post noise.

---

### 1.4 Best Post Days

```
avg_er_by_day[d] = SUM(ER_post_i  where weekday(post_i.posted_at) == d)
                   ──────────────────────────────────────────────────────
                   COUNT(posts where weekday(posted_at) == d)

best_post_days = top_3 days ranked by avg_er_by_day[d]  (descending)
```

---

### 1.5 Top Content Formats

```
format_count[f]  = COUNT(posts where format == f)
format_share[f]  = format_count[f] / total_posts

top_content_formats = formats sorted by format_share DESC, take top 3
```

---

### 1.6 Tone Fingerprint

Rule-based keyword matching against curated word lists per tone bucket:

```
tone_score[t] = COUNT(words in post_text that appear in tone_wordlist[t])
                ──────────────────────────────────────────────────────────
                total_word_count(post_text)

tone_fingerprint[t] = MEAN( tone_score[t] across all posts in window )
```

**Tone buckets:** `formal`, `casual`, `humorous`, `educational`, `motivational`

**Normalise so all tones sum to 1.0:**
```
tone_fingerprint[t] = raw_tone[t] / SUM(raw_tone[t] for all t)
```

---

### 1.7 Audience Geography

Pulled directly from Telegram API (`getChatAdministratorsCount` stats if available) or TGStat. No calculation needed — stored as returned, top 3 countries by share.

---

### 1.8 Subscriber Growth Curve

```
growth_curve entry per month:
  subs[m]       = subscriber_count at end of month m
  monthly_delta = subs[m] - subs[m-1]
  monthly_pct   = (subs[m] - subs[m-1]) / subs[m-1] × 100
```

---

## 2. Competitor Intelligence — Ranking Score

Each competitor gets a composite rank score (0–100):

```
W_subs      = 0.35    // weight: subscriber count relative to peers
W_er        = 0.35    // weight: engagement rate
W_freq      = 0.15    // weight: posting frequency (activity signal)
W_relevance = 0.15    // weight: keyword overlap with our channel's niche
```

### 2.1 Normalise each metric (min-max across discovered competitors)

```
norm(x) = (x - min_x) / (max_x - min_x)

norm_subs[c]      = norm(competitor_c.subscriber_count)
norm_er[c]        = norm(competitor_c.avg_er)
norm_freq[c]      = norm(competitor_c.post_frequency_per_day)
norm_relevance[c] = norm(keyword_overlap_score[c])     // see §2.2
```

### 2.2 Keyword Overlap Score (Relevance)

```
channel_keywords    = set of category + sub_category keywords + top topics
competitor_keywords = set of top_content_themes from competitor record

intersection = |channel_keywords ∩ competitor_keywords|
union        = |channel_keywords ∪ competitor_keywords|

keyword_overlap_score[c] = intersection / union      // Jaccard similarity
```

### 2.3 Competitor Rank Score

```
rank_score[c] = ( W_subs      × norm_subs[c]
               +  W_er        × norm_er[c]
               +  W_freq      × norm_freq[c]
               +  W_relevance × norm_relevance[c] ) × 100

competitors sorted by rank_score DESC → assign rank 1, 2, 3 ...
```

---

## 3. Analytics Agent Calculations

### 3.1 Subscriber Delta

```
subscriber_delta     = current_count - previous_count
subscriber_delta_pct = subscriber_delta / previous_count × 100
```

**Where previous_count** = subscriber_count from last snapshot of same type (daily vs weekly).

---

### 3.2 Average Views per Post (Rolling)

```
avg_views = SUM(views_i for posts in period) / COUNT(posts in period)
```

---

### 3.3 Reach Estimation

Telegram does not expose unique reach directly. Estimate:

```
reach_per_post   = views × reach_multiplier

reach_multiplier = 1.0  if forwards == 0
                 = 1.0 + (forwards / subscriber_count) × 5.0  otherwise

period_reach     = MAX(reach_per_post_i for all posts in period)
                   // best single-post reach as proxy for period reach
```

---

### 3.4 Churn Signal Detection

```
rolling_avg_unsub_rate = MEAN(subscriber_delta_pct over last 4 same-type snapshots)
                         // use absolute value, treat negative delta as unsub

churn_rate[current] = ABS(MIN(subscriber_delta_pct, 0))

churn_signal = true   IF churn_rate[current] > 2 × ABS(rolling_avg_unsub_rate)
                      AND subscriber_delta < 0
             = false  otherwise
```

---

### 3.5 Insight Rules (auto-generated text triggers)

Computed as boolean flags that map to pre-written insight templates:

```
RULE 1  — best_growth_day
  IF subscriber_delta_pct == MAX(subscriber_delta_pct over last 30 daily snapshots)
  → insight: "Best single-day gain this month"

RULE 2  — er_drop
  IF avg_er[current] < avg_er[previous] × 0.70       // dropped >30%
  → insight: "ER fell >30% vs last period"

RULE 3  — er_spike
  IF avg_er[current] > avg_er[previous] × 1.30
  → insight: "ER up >30% vs last period"

RULE 4  — format_winner
  best_format = format with highest avg ER this period
  worst_format = format with lowest avg ER this period
  IF er[best_format] > er[worst_format] × 2.0
  → insight: "{best_format} outperforming {worst_format} 2×"

RULE 5  — low_post_volume
  IF total_posts < ROUND(post_frequency_per_day × days_in_period × 0.6)
  → insight: "Post volume 40% below target cadence"

RULE 6  — churn_alert
  IF churn_signal == true
  → insight: "Churn spike detected — unsubscribes 2× rolling average"
```

---

## 4. Strategy Agent Calculations

### 4.1 Recommended Post Frequency

```
base_freq = channel_dna.post_frequency_per_day

// Adjust up if growth is strong
growth_boost = 0.0
IF subscriber_delta_pct > 5   → growth_boost = +0.5
IF subscriber_delta_pct > 10  → growth_boost = +1.0

// Adjust down if ER is dropping
er_penalty = 0.0
IF avg_er < 1.5               → er_penalty = -0.5

recommended_freq = MAX(1.0, base_freq + growth_boost - er_penalty)
recommended_freq = MIN(recommended_freq, 5.0)   // hard cap 5 posts/day
```

---

### 4.2 Content Mix Calculation

Base weights derived from DNA top_content_formats, boosted or penalised by ER:

```
for each format f in [article, poll, meme, video, link]:
  base_weight[f]  = channel_dna.top_content_formats.share[f]  (0 if absent)
  er_boost[f]     = (avg_er_by_format[f] - channel_avg_er) / channel_avg_er

  adjusted_weight[f] = base_weight[f] × (1 + er_boost[f])

// Normalise to sum = 1.0
content_mix[f] = adjusted_weight[f] / SUM(adjusted_weight[f'] for all f')

// Convert to percentage slots
slots_per_format[f] = ROUND(content_mix[f] × total_posts_in_period)
```

---

### 4.3 Post Slot Assignment (Time of Day)

```
// Score each hour slot for the day
slot_score[h] = channel_dna.avg_er_by_hour[h]

// Pick N slots (= recommended_freq) that are:
//   a) highest scoring
//   b) at least 3 hours apart (no clustering)

selected_slots = greedy_select(
  slots    = all 24 hours,
  score_fn = slot_score[h],
  n        = recommended_freq,
  min_gap  = 3    // hours between slots
)
```

---

## 5. Content Intelligence — 7-Signal Scoring

Each signal returns **1 (pass)** or **0 (fail)**.

---

### Signal 1: Relevance

```
channel_topics = set of primary_topics from current strategy
item_topics    = content_item.topics   (tags from classifier)

overlap        = |channel_topics ∩ item_topics|

relevance = 1   IF overlap >= 1
          = 0   otherwise
```

---

### Signal 2: Freshness

```
age_hours = (NOW() - content_item.published_at) / 3600

freshness = 1   IF age_hours <= 48
          = 0   IF age_hours >  48
```

**Extended rule for evergreen formats (strategy_task.format == 'educational'):**
```
freshness = 1   IF age_hours <= 168   (7 days)
```

---

### Signal 3: Novelty

Check if a near-duplicate was already published or queued by this channel.

```
// Use title fingerprint: normalise → strip stopwords → sort tokens → hash
fingerprint(text) = SHA256( SORT( TOKENISE( LOWERCASE( STRIP_STOPWORDS(text) ) ) ) )

item_fp = fingerprint(content_item.title + content_item.body_text[:200])

recent_fps = SET of fingerprint(gp.post_text) for generated_posts
             where channel_id == this_channel
             and created_at > NOW() - 30 days

// Jaccard similarity check against each recent post
for fp in recent_fps:
  sim = jaccard(item_fp_tokens, fp_tokens)
  IF sim > 0.65  → novelty = 0  (too similar, STOP)

novelty = 1   // if no match found
```

---

### Signal 4: Goal Alignment

```
strategy_topics  = current strategy.primary_topics   (list of strings)
item_topics      = content_item.topics

goal_match = |strategy_topics ∩ item_topics| / |strategy_topics|

goal_alignment = 1   IF goal_match >= 0.33   (at least 1 of 3 topics match)
               = 0   otherwise
```

---

### Signal 5: Virality

Score the source content's inherent shareability based on available engagement signals.

**Case A — Source has engagement metrics (competitor posts or known platforms):**
```
share_ratio    = forwards / MAX(views, 1)
reaction_ratio = reactions / MAX(views, 1)

virality_raw = (share_ratio × 0.6) + (reaction_ratio × 0.4)

virality = 1   IF virality_raw >= 0.02    // ≥2% forward/reaction rate
         = 0   otherwise
```

**Case B — Source has no engagement metrics (RSS, website):**
```
// Proxy: title contains hook pattern (rule-based regex match)
HOOK_PATTERNS = [
  r"\d+ (ways|tools|tips|reasons|mistakes)",   // listicle
  r"(how to|why|what happens when)",            // curiosity gap
  r"(breaking|just in|thread)",                 // news hook
  r"(you (need|must|should)|everyone)",         // authority hook
]

hook_matches = COUNT(patterns that match LOWERCASE(content_item.title))

virality = 1   IF hook_matches >= 1
         = 0   otherwise
```

---

### Signal 6: Competitor Set

Check whether top competitors have recently posted the same content.

```
competitor_fps = SET of fingerprint(cp.text_preview)
                 for competitor_posts
                 where competitor.channel_id == this_channel
                 and cp.posted_at > NOW() - 7 days

item_fp_tokens = TOKENISE(content_item.title + content_item.body_text[:200])

for cfp in competitor_fps:
  sim = jaccard(item_fp_tokens, cfp_tokens)
  IF sim > 0.60  → competitor_set = 0  (competitor already posted it, STOP)

competitor_set = 1   // unique vs competitor set
```

---

### Signal 7: Brand Safety

```
BLOCK_KEYWORDS = [
  // violence, adult, illegal, spam, scam, misinformation triggers
  "adult", "porn", "xxx", "gambling", "casino", "drugs", "weapon",
  "kill", "bomb", "hack your", "get rich quick", "100% returns",
  "guaranteed profit", "MLM", "pyramid", "click here to earn",
  "free money", "nude", "explicit"
  // extend per channel category
]

text_lower = LOWERCASE(content_item.title + " " + content_item.body_text[:500])

blocked_hits = COUNT(kw for kw in BLOCK_KEYWORDS if kw in text_lower)

brand_safety = 0   IF blocked_hits >= 1
             = 1   otherwise
```

---

### 5.1 Total Score & Pass Decision

```
total_score = relevance + freshness + novelty + goal_alignment
            + virality + competitor_set + brand_safety        // max = 7

threshold = channel.score_threshold   // default = 4

passed = true   IF total_score >= threshold
       = false  otherwise
```

---

### 5.2 Source Quality Score (rolling feedback)

Updated after every content_score record for items from that source:

```
new_avg = (source.avg_quality_score × source.total_items_scored + total_score)
          ─────────────────────────────────────────────────────────────────────
                          (source.total_items_scored + 1)

source.avg_quality_score  = new_avg
source.total_items_scored = source.total_items_scored + 1
```

**Auto-deactivate rule:**
```
IF source.avg_quality_score < 2.5  AND  source.total_items_scored >= 20
→ source.is_active = false
→ agent_run insight: "Source {name} auto-paused (avg score {avg_quality_score:.1f}/7)"
```

---

## 6. Competitor Post ER (for competitor_posts table)

```
er = (reactions_count + forwards) / MAX(views, 1) × 100
```

Stored on ingest; used as virality proxy and competitive benchmark.

---

## 7. Quick Reference — All Formulas

```
─────────────────────────────────────────────────────────────────────────────
METRIC                  FORMULA
─────────────────────────────────────────────────────────────────────────────
ER per post             (reactions + forwards + replies) / views_capped × 100
Channel avg ER          MEAN(ER_post) over last 30 days
Post frequency          total_posts / days_in_period
Best post hour          argmax_h( avg ER grouped by UTC hour )
Best post days          top 3 weekdays by avg ER
Format share            format_count[f] / total_posts
Tone score              matching_words[tone] / total_words  (normalised)
Subscriber delta        current - previous
Subscriber delta %      (current - previous) / previous × 100
Reach per post          views × (1 + forwards/subs × 5)
Churn signal            churn_rate > 2 × rolling_avg_churn_rate
Keyword overlap         |A ∩ B| / |A ∪ B|   (Jaccard)
Competitor rank         0.35×norm_subs + 0.35×norm_er + 0.15×norm_freq + 0.15×norm_relevance
Rec. post frequency     CLIP( base_freq + growth_boost - er_penalty,  1.0, 5.0 )
Content mix weight      base_share[f] × (1 + ER_boost[f]),  normalised to 1.0
Signal: Relevance       1 if channel_topics ∩ item_topics ≥ 1
Signal: Freshness       1 if age_hours ≤ 48  (168 for evergreen)
Signal: Novelty         1 if MAX Jaccard similarity vs recent posts < 0.65
Signal: Goal Align      1 if topic_overlap / strategy_topics ≥ 0.33
Signal: Virality        1 if share_ratio ≥ 0.02  OR hook_pattern match ≥ 1
Signal: Competitor Set  1 if MAX Jaccard similarity vs competitor posts < 0.60
Signal: Brand Safety    1 if no block_keyword found in text
Total content score     SUM of 7 signals  (0–7)
Pass threshold          total_score ≥ channel.score_threshold  (default 4)
Source quality (EMA)    running average of total_score per source
Competitor post ER      (reactions + forwards) / MAX(views,1) × 100
─────────────────────────────────────────────────────────────────────────────
```