# Skill: Channel Classification

## Purpose

Classify the Telegram channel into a structured profile that all downstream pipeline stages use as their foundational context. Without accurate classification, every subsequent analysis stage — content scoring, competitor discovery, benchmarking, growth analysis — will produce irrelevant or misleading outputs.

This skill is the lens through which the agent understands what kind of channel it is analyzing and what success looks like for that channel type.

---

## When This Skill Runs

- On the first pipeline run after channel connection (initial classification)
- Once per week thereafter (to detect classification drift — channels evolve over time)
- On demand if the operator signals a strategic pivot

---

## Inputs Required

| Input | Source | Description |
|---|---|---|
| `channel.title` | Telegram MTProto API | Channel display name |
| `channel.description` | Telegram MTProto API | Channel bio / about text |
| `channel.subscriber_count` | Telegram MTProto API | Current subscriber count |
| `channel.creation_date` | Telegram MTProto API | When the channel was created |
| `posts_sample` | Data collection stage | 50 most recent posts — full text, media type, link presence |
| `operator_stated_goal` | User setup input | Optional — operator's stated primary goal |

---

## Classification Dimensions

The skill classifies the channel across six independent dimensions:

### Dimension 1 — Primary Category

The broad content domain the channel operates in.

| Category | Description |
|---|---|
| Deals & Affiliate | Product deals, discount alerts, coupon codes, affiliate product promotion |
| News & Media | Breaking news, current affairs, commentary, journalism |
| Education | Tutorials, how-to content, courses, study material, skill development |
| Entertainment | Humor, memes, pop culture, viral content, storytelling |
| Finance & Investment | Market analysis, stock picks, crypto signals, personal finance |
| Health & Wellness | Fitness, nutrition, mental health, medical information |
| Technology | Tech news, product reviews, developer content, software |
| Community & Interest | Hobby groups, fan communities, regional groups, special interest |
| Business & Corporate | Company updates, product announcements, B2B content |
| Personal Brand | Individual creator content, opinions, lifestyle, personal updates |
| Other | Does not fit the above categories |

### Dimension 2 — Subcategory

A more specific classification within the primary category. The agent derives this from post content rather than selecting from a fixed list, because subcategories are highly niche-specific. Examples:

- Deals & Affiliate → Mobile Accessories / Fashion / Home Appliances / Books
- News & Media → Indian Politics / Global Tech News / Sports News / Business
- Education → UPSC Preparation / Python Programming / Design / English Language

### Dimension 3 — Geographic Focus

| Value | Description |
|---|---|
| Hyper-local | City or region-specific content |
| National | Single country focus |
| Regional | Multi-country regional focus (e.g., South Asia, Southeast Asia) |
| Global | No geographic restriction |

### Dimension 4 — Channel Maturity

Determined by channel age and subscriber count together:

| Maturity Stage | Age + Size Criteria |
|---|---|
| New | Under 6 months old OR under 1,000 subscribers |
| Growing | 6–18 months old AND 1,000–50,000 subscribers |
| Established | 18 months–4 years AND 50,000–500,000 subscribers |
| Mature | Over 4 years OR over 500,000 subscribers |

### Dimension 5 — Primary Goal

The channel's implicit or explicit primary objective, inferred from content patterns:

| Goal | Signal |
|---|---|
| Subscriber Growth | High post frequency, strong call-to-action language, share-oriented content |
| Engagement | Interactive content (polls, questions), reaction-heavy posts, community-building tone |
| Link Clicks / Monetization | High affiliate link density, product-focused content, price/deal framing |
| Retention | Consistent editorial calendar, deep content, repeat topic series |
| Brand Awareness | Branded content, announcement-heavy, one-way communication style |

### Dimension 6 — Content Style

| Style | Description |
|---|---|
| Text-heavy | Most posts are primarily text with minimal media |
| Media-heavy | Most posts are photos or videos with minimal text |
| Link-heavy | Most posts contain outbound links as the primary payload |
| Mixed | Balanced combination of text, media, and links |
| Poll-centric | Regular use of polls and interactive formats |

---

## Classification Logic

The agent does not match against a rigid ruleset. It reasons over the available data and reaches a classification judgment, weighing:

1. **Channel description signals** — explicit category claims, stated topics, keywords
2. **Post content patterns** — what topics and products appear across the post sample
3. **Post structure patterns** — what formats dominate (text blocks, image + caption, link-only, poll)
4. **Engagement pattern shape** — which content types attract the most reactions and forwards (reveals what the audience values, which in turn reveals what the channel is actually delivering)
5. **Operator-stated goal** — if provided, used as a prior that the content evidence either confirms or contradicts

When evidence conflicts (e.g., the description says "news channel" but 80% of posts are product deals), the agent prioritizes the content evidence over the stated description.

---

## Outputs

```
channel_profile:
  category: string               # Primary category from taxonomy
  subcategory: string            # Derived subcategory (freeform)
  geography: string              # Geographic focus
  maturity: string               # Maturity stage
  primary_goal: string           # Primary goal
  content_style: string          # Content style
  audience_type: string          # One-line audience description
  confidence: float              # Classification confidence 0.0–1.0
  classification_notes: string   # Key evidence supporting classification
```

### Audience Type

A brief natural language description of the likely audience, inferred from content and engagement data. Examples:

- "Deal-seeking mobile accessory buyers in India looking for the best price before purchase"
- "Professionals following Indian financial markets and seeking actionable stock ideas"
- "UPSC aspirants looking for structured daily current affairs summaries"

This description is used downstream by the audience intelligence and recommendation skills.

---

## Confidence Scoring

| Confidence Range | Meaning |
|---|---|
| 0.85–1.00 | High confidence — clear, consistent signals across all dimensions |
| 0.65–0.84 | Moderate confidence — most signals align, minor ambiguity in subcategory or goal |
| 0.40–0.64 | Low confidence — signals are mixed or insufficient data; classification is a best estimate |
| Below 0.40 | Very low — channel is too new, too sparse, or too eclectic to classify reliably |

When confidence is below 0.65, downstream stages are notified and reduce their own confidence outputs accordingly. The weekly report flags the channel as "classification pending more data" for new channels.

---

## Classification Drift Detection

On weekly re-runs, the agent compares the new classification output against the stored classification. If any dimension changes, it evaluates whether this is:

- **Genuine drift** — the channel's strategy has changed (e.g., a news channel has pivoted to deals)
- **Natural evolution** — the channel has matured into a new tier
- **Data noise** — temporary content mix variation that does not represent a strategic change

Genuine drift triggers a full re-run of all downstream stages to update the channel's intelligence picture. Natural evolution updates only the maturity dimension. Data noise is logged but does not trigger downstream updates.

---

## Downstream Dependencies

The `channel_profile` output is injected into:

- **Stage 3 (Audience Intelligence)** — audience type framing
- **Stage 4 (Content Intelligence)** — category taxonomy construction
- **Stage 5 (Competitor Intelligence)** — keyword extraction for competitor discovery, competitor size filter calibration
- **Stage 6 (Benchmark Engine)** — benchmark cohort construction (category + subcategory + geography + maturity)
- **Stage 7 (Growth Analysis)** — growth metric interpretation varies by channel type
- **Stage 8 (Retention Analysis)** — retention benchmarks and fatigue thresholds are category-dependent
- **Stage 10 (Recommendation Engine)** — all recommendations are framed relative to channel type and goal
