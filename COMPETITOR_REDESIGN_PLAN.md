# Competitor Agent Redesign + Flow Improvement — TODO

> Captured from user feedback (before a /compact). Implement this next.

## User requirements (verbatim intent)
1. **Competitor agent is NOT independent** — it must run **after Channel DNA**.
   Once DNA finds the **category/brand**, the competitor agent runs, finds
   **benchmarks + gaps**, and feeds them to the **Strategy agent**, which sets
   targets/benchmarks against competitors. 
2. **Discovery must be brand-centric web search**, NOT direct Telegram-channel
   keyword search:
   - Web-search the **real top-10 competitor brands/companies** of the channel's
     brand in its category (e.g. for GrabOn → CashKaro, CouponDunia, Zingoy…).
   - Then, **for each competitor brand, find that brand's Telegram channel**
     (web-search "{brand} official telegram channel" → resolve real t.me handle).
   - Direct Telegram keyword search is only a last-resort fallback.
3. The overall flow "is not good, something is missing" → make it a **complete,
   coherent Telegram growth & retention agent** (growth + retention, benchmarks
   feeding strategy, gaps covered).

## New competitor flow
```
DNA → category/brand
  ↓
Competitor agent
  1. discover_competitor_brands(brand, category, topics)
        web-search context (ddgs) + Groq LLM → list of REAL competitor brand names
  2. for each brand: find_brand_telegram(brand, client)
        web-search "{brand} official telegram channel" → extract t.me handle
        fallback: Telegram search by brand name; verify via get_telegram_channel_info
  3. enrich (members, top posts, metrics); skip <100 members / unresolved
  4. rank_competitors (existing weighted formula)
  5. compute_benchmarks(competitors, my_dna)
        competitor avg subs/ER/frequency, my ER gap, gap_topics, top_competitor
  6. save_competitors (+ store brand + benchmark summary)
  ↓
Strategy agent
  - target ER set against competitor_avg_er (close the gap)
  - primary_topics include competitor gap_topics (already partial)
  - mirror top-ER competitor format (tactic exists)
  - surface benchmark in goal/output
```

## Files to change
- `tools/competitor.py`
  - ADD `discover_competitor_brands(brand, category, topics)` — ddgs context + `tools.llm.chat_complete` → JSON brand list (`_parse_brand_list`).
  - ADD `find_brand_telegram(brand, client)` — ddgs "{brand} telegram" → `extract_telegram_usernames`; fallback `search_telegram_channels`.
  - ADD `compute_benchmarks(competitors, my_dna)` (pure) → benchmark dict.
  - Demote `search_competitors_duckduckgo`/`search_telegram_channels` to fallback only.
- `tools/channels.py` — `get_channel_context` must also return `display_name` (the brand).
- `agents/competitor_intelligence.py` — rewrite `_run` to use brand-centric discovery;
  guard on category (if missing, detect from recent posts via `get_channel_category`);
  return `benchmarks` in result.
- `tools/strategy.py` / `agents/strategy.py` — use competitor benchmark (target ER vs
  competitor avg) in `compute_strategy` goal + tactics; gap topics already wired.
- Tests:
  - `tests/test_competitor.py` — add `compute_benchmarks` + `_parse_brand_list` tests.
  - `tests/test_e2e.py` — patch new discovery fns (`discover_competitor_brands` → [],
    `find_brand_telegram`) instead of the old `search_*`.
- README — document the corrected brand-centric competitor flow.

## Retention angle (the "something missing")
- Growth is well covered; strengthen **retention**: churn already detected
  (analytics) + `strategy_reset` tactic. Consider explicit re-engagement content
  tactic when churn_signal is true, and a retention KPI on the dashboard.

## Reliability note (free web search)
- Discovery uses free DuckDuckGo (`ddgs`), which **rate-limits aggressively**.
  Mitigations added: throttle (`_SEARCH_MIN_INTERVAL`), retry/backoff in
  `_web_search`, fewer high-yield searches (1/brand, top-12 brands, 1 curated),
  and brand-match validation (drops noise like `@Apple_iphone74`).
- Yield still varies run-to-run when DDGS throttles. For CONSISTENT high yield,
  wire a paid search API (Brave/Serp/Bing) via env — recommended next step.

## Topic accuracy
- DNA now prefers `llm_extract_topics` (Groq) → clean phrases
  ("Amazon Electronics Deals", "Women's Fashion Clothing"); falls back to
  rule-based `extract_top_topics` (now drops vowel-less code tokens).

## Status: ✅ DONE (discovery reliability tuning may continue — see note)
- Brand-centric discovery implemented (`discover_competitor_brands` + `find_brand_telegram`).
- `compute_benchmarks` added; benchmarks feed Strategy (target ER, close_er_gap tactic).
- DNA now mines `top_topics` (specific) → Strategy `primary_topics` → Content.
- Retention: `re_engage` tactic on churn.
- Verified live on @GrabOnIndiaOfficial: found DesiDime / FreeKaaMaal / CouponDunia.
- Tests: 64 passed.
