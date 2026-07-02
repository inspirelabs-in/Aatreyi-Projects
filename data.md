# Data sources — what comes from Telegram vs. what we compute

This documents, per surface, which numbers are **read directly from Telegram** and
which are **derived/computed by our own logic** (or come from other external
sources). "Telegram" means the channel's own data pulled via the Telegram user
session (Telethon) — or, for competitors, the public `t.me/s/<handle>` web preview.

---

## 1. Raw, straight from Telegram (we do not invent these)

| Field | Source | Notes |
|---|---|---|
| Channel title, `@username`, Telegram ID | Telegram (Telethon) | Channel metadata |
| Subscriber / member count | Telegram | Sampled every ~20 min → the growth series |
| Post text / caption | Telegram | The actual message content |
| Post media type (photo / text / poll / …) | Telegram | Used for "engagement by format" |
| Post timestamp (date/time) | Telegram | |
| **Views** per post | Telegram | Basis for every engagement ratio |
| **Reactions** count per post | Telegram | |
| **Forwards** count per post | Telegram | |
| Poll options + total voters | Telegram | Basis for poll participation |
| Competitor member count + recent posts/views | Telegram public web (`t.me/s`) | No login; scraped when a handle resolves |

## 2. Computed by us (derived from the raw Telegram data above)

| Metric | How we compute it | Where it shows |
|---|---|---|
| Engagement rate (ER) | reactions (+ interactions) ÷ views | Dashboard, Strategy benchmark |
| Reaction density | avg(reactions ÷ views) across posts | Intelligence → Community signal |
| Forward rate | avg(forwards ÷ views) | Intelligence → Community signal |
| Poll participation | avg voters ÷ member count | Intelligence → Community signal |
| Community state (active / quiet / silent) | thresholds on reaction density & forward rate | Intelligence, Strategy |
| Viral spikes | posts whose engagement spikes vs. the channel's norm | Intelligence |
| Post purpose mix (conversion / retention / standard) | our classifier over each post's text/format | Intelligence |
| Engagement by format | ER grouped by post format | Intelligence |
| Engagement by topic | ER grouped by detected topic (empty if none detected) | Intelligence |
| Growth curve / subscriber trend | time series of the sampled subscriber counts | Dashboard |
| Benchmarks (your ER vs competitor avg vs target) | our aggregation | Strategy |
| Channel DNA (category, tone, top topics, best hours) | inferred from the channel's own posts | Onboarding / Strategy inputs |
| Competitor intelligence (content gaps, emerging trends, opportunities, best hours/media/CTA) | aggregated across competitors — **guidance only, never copied** | Strategy → Competitors |
| Strategy plan (slots, timing window, media mix, priority, rationale) | the Strategy agent (planner) | Strategy → Execution plan |
| Retention plan (habit-loop slots) | the Strategy agent from engagement patterns | Intelligence → Retention |

## 3. From other external sources (not Telegram)

| Field | Source | Notes |
|---|---|---|
| Deal products (title, price, discount %, image, product URL) | Amazon / Flipkart scraping (Playwright + httpx) | The deals themselves |
| Affiliate links (Amazon `tag`, Flipkart `affid`) | our generation | Appended to product URLs |
| Shortened links (`grbn.in`) | GrabOn shortener API | Applied after affiliate generation; fails open to the raw link if the datacenter is Cloudflare-blocked |
| Post captions / hooks / CTAs | Groq LLM (llama-3.3-70b) | Shaped by Strategy Context; deal facts stay factual |

---

### Quick rule of thumb
- **Counts and raw post metadata** (views, reactions, forwards, subscribers, timestamps, media type) → **Telegram**.
- **Any rate, percentage, classification, trend, benchmark, plan, or label** → **computed by us** from those raw counts.
- **Deals, affiliate/short links, and captions** → **external** (marketplaces, GrabOn shortener, LLM), not Telegram.
