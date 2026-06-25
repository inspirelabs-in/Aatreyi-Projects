# Telegram Growth & Retention Agent — Implementation Roadmap

---

## Tech Stack Decision

| Layer | Choice | Reason |
|---|---|---|
| Language | **Python 3.11+** | Telethon, APScheduler, feedparser all native |
| Framework | **FastAPI** | Async, lightweight, easy webhook endpoints |
| Database | **PostgreSQL 15** | Relational, JSONB for flexible columns |
| ORM | **SQLAlchemy 2 + Alembic** | Typed models, migrations |
| Task queue | **Redis + RQ** | Simple queue for post slots and agent jobs |
| Telegram lib | **Telethon** (MTProto) + **python-telegram-bot** (Bot API) | Telethon for listening/history, Bot API for publishing |
| Scheduler | **APScheduler** | Cron + interval jobs in-process |
| Scraping | **httpx + BeautifulSoup4 + feedparser** | RSS, HTML pages |
| LLM | **Anthropic Claude API** (tool_use) | 2 LLM tools: generate_post, generate_original_post |
| Search fallback | **DuckDuckGo DDGS** (free, no API key) | Competitor discovery |
| Web UI | **Next.js 14 + Tailwind** | Dashboard we designed |
| Hosting | **Railway / Render / VPS** | One container per service |

---

## Agent Dependency Layers (Implementation Order)

```
Layer 0: Infrastructure (DB, shared tools, scheduler)
    ↓
Layer 1: Channel DNA Agent  ──►  Competitor Intelligence  ──►  Analytics Agent
    (independent, run in parallel)
    ↓
Layer 2: Strategy Agent
    (blocked by all Layer 1)
    ↓
Layer 3: Content Intelligence Agent
    (blocked by Strategy)
    ↓
Layer 4: Review Queue + Publisher
    ↓
Layer 5: Web UI / Dashboard
```

---

## Phase 0 — Project Setup (Days 1–3)

**Goal:** Working skeleton, nothing breaks.

### Tasks
- [ ] Create monorepo: `telegram-growth-agent/`
- [ ] Directory structure:
  ```
  agents/        ← one file per agent
  tools/         ← all tool implementations
  db/            ← models + migrations
  scheduler/     ← cron jobs
  api/           ← FastAPI app (webhooks, UI backend)
  ui/            ← Next.js dashboard
  config.py      ← env vars
  ```
- [ ] `.env` setup: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `BOT_TOKEN`, `ANTHROPIC_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `TGSTAT_API_KEY`, `TELEMETR_API_KEY`
- [ ] Postgres + Redis running (Docker Compose for local dev)
- [ ] `alembic init` + first empty migration

### Deliverable
`docker-compose up` starts DB + Redis. `python -c "from config import settings; print(settings)"` passes.

---

## Phase 1 — Database Models + Shared Tools (Days 4–8)

**Goal:** All 14 DB tables created. 3 shared tools working.

### DB Models (SQLAlchemy)
Implement these in `db/models.py`:

```
channels, channel_dna, competitors, competitor_posts,
analytics_snapshots, strategies, strategy_tasks,
content_sources, content_items, content_scores,
generated_posts, post_queue, agent_runs, cron_jobs
```

Run `alembic revision --autogenerate` + `alembic upgrade head`.

### Shared Tools (`tools/shared.py`)
- `get_telegram_channel_info(username)` — Telethon `GetFullChannelRequest`
- `get_channel_posts(username, limit, since_date)` — Telethon `GetHistoryRequest`
- `log_agent_run(agent_name, channel_id, status, meta)` — DB insert to `agent_runs`

### Agent Runner Base (`agents/base.py`)
```python
class BaseAgent:
    async def run(self, channel_id: int) -> dict: ...
    async def _before_run(self): ...   # log start
    async def _after_run(self, result): ...  # log end + status
```

### Deliverable
`alembic upgrade head` creates all 14 tables. `pytest tests/test_shared_tools.py` passes with a real Telegram API call (use a test channel).

---

## Phase 2 — Channel DNA Agent (Days 9–12)

**Goal:** Agent profiles a channel — metrics, niche, tone, audience fingerprint — and saves to DB.

### Tools to implement (`tools/channel_dna.py`)
1. `get_tgstat_channel_stats(username)` — TGStat API call, fallback to empty dict
2. `compute_channel_dna(posts[], member_count, tgstat_data)` — pure rule-based:
   - ER = `(avg_views / member_count) * 100`  (cap views at 2× members)
   - `post_frequency` = posts in last 30d / 30
   - `best_hour` = argmax over hour buckets
   - `best_days` = top 3 days by avg ER
   - `format_share` = count by type / total
   - `tone_fingerprint` = keyword wordlist match → normalise to [0,1]
3. `save_channel_dna(channel_id, dna_dict)` — upsert to `channel_dna`
4. `get_channel_category(username, posts_sample)` — keyword rules → category string
5. `detect_tier(member_count)` → `"A"` if < 5000 else `"B"` if < 50000 else `"C"`
6. `get_disappearing_message_flag(username)` — check `has_disappearing_messages` in channel info

### Tier A vs B/C routing
```python
if tier == "A":
    onboarding_data = await collect_user_input()  # username, category, goal
else:
    channel_data = await get_telegram_channel_info(username)
```

### Deliverable
`python -m agents.channel_dna --channel @techdigest_in` prints DNA dict + saves row in `channel_dna`.

---

## Phase 3 — Competitor Intelligence Agent (Days 13–17)

**Goal:** Discovers top 10 relevant competitors, ranks them, saves to DB.

### Tools to implement (`tools/competitor.py`)
1. `search_competitors_duckduckgo(niche, category, keywords[])` — DDGS text search → extract @usernames from snippets
2. `search_telegram_channels(query)` — `SearchPublicRequest` via Telethon
3. `get_tgstat_similar_channels(username)` — TGStat `/channels/similar`
4. `get_telemetr_similar_channels(username)` — Telemetr API
5. `get_competitor_posts(username, limit)` — reuse shared `get_channel_posts`
6. `compute_competitor_metrics(posts[], member_count)` — same formulas as DNA
7. `rank_competitors(competitors[])`:
   ```
   score = 0.35 × norm_subs + 0.35 × norm_er + 0.15 × norm_freq + 0.15 × norm_relevance
   ```
   `norm_*` = min-max normalise across the candidate set
8. `save_competitors(channel_id, ranked_list[])` — upsert `competitors`
9. `flag_disappearing_messages(username)` — sets `has_disappearing_messages=True`, applies rank penalty × 0.7
10. `dedup_competitor_list(candidates[])` — remove already-tracked channels

### Fallback chain logic
```python
results = await ddg_search(...)
if len(results) < 5:
    results += await telegram_search(...)
if len(results) < 5:
    results += await tgstat_similar(...)
if len(results) < 5:
    results += await telemetr_similar(...)
```

### Deliverable
`python -m agents.competitor_intelligence --channel @techdigest_in` saves 10 ranked rows in `competitors`.

---

## Phase 4 — Analytics Agent (Days 18–21)

**Goal:** Calculates growth delta, ER, churn signals, emits insights.

### Tools to implement (`tools/analytics.py`)
1. `compute_analytics_snapshot(channel_id, current_stats, history[])`:
   - `sub_delta` = current − previous snapshot
   - `sub_delta_pct` = delta / previous × 100
   - `reach_estimate` = avg_views / member_count
   - `churn_signal` = True if `sub_delta < 0` and `|delta| > 2 × rolling_avg_delta`
   - 6 insight rules → list of insight strings
2. `save_analytics_snapshot(channel_id, snapshot_dict)` — insert `analytics_snapshots`
3. `get_analytics_history(channel_id, n=30)` — fetch last N snapshots
4. `compute_er_by_format(posts[])` — group by format → avg ER per format
5. `compute_best_slots(posts[])` — argmax ER over hour × day matrix
6. `flag_strategy_review(channel_id, reason)` — sets `needs_strategy_review=True` in `channels`
7. `generate_analytics_digest(snapshot, insights[])` — template-based text summary (no LLM)

### Deliverable
`python -m agents.analytics --channel @techdigest_in` prints snapshot + saves to `analytics_snapshots`. `flag_strategy_review` tested via pytest.

---

## Phase 5 — Strategy Agent (Days 22–25)

**Goal:** Produces a weekly action plan, post slots, content mix. Blocked by Phases 2–4.

### Tools to implement (`tools/strategy.py`)
1. `compute_strategy(channel_dna, analytics_snapshot, competitors[])`:
   - `posting_cadence` = ceil(`target_er` / current ER × current freq)
   - `content_mix` = weighted by format ER from analytics
   - `post_slots` = best hours × days from analytics
   - `focus_topics` = niche gaps vs competitors (Jaccard complement)
   - `growth_tactics` = rule table (ER < 3% → increase polls; churn → reduce freq; etc.)
2. `save_strategy(channel_id, strategy_dict)` — upsert `strategies`, insert `strategy_tasks`
3. `archive_old_strategy(channel_id)` — mark previous as `archived`
4. `get_active_strategy(channel_id)` — fetch current strategy
5. `update_cron_for_content_agent(channel_id, post_slots[])` — upsert `cron_jobs` rows
6. `get_competitor_gap_topics(my_dna, competitors[])` — Jaccard complement on topic sets

### Strategy rules table (implement as Python dict lookup)
| Condition | Action |
|---|---|
| ER < 3% | Increase polls to 40% mix |
| ER > 8% | Hold format mix |
| sub_delta < 0 for 3 days | Reduce posting freq by 1/day |
| churn_signal = True | Trigger full strategy reset |
| competitor overtook on ER | Mirror top-ER format of that competitor |

### Deliverable
`python -m agents.strategy --channel @techdigest_in` prints strategy dict + saves to DB. `cron_jobs` rows created for all post slots.

---

## Phase 6 — Content Intelligence Agent (Days 26–33)

**Goal:** Per-slot: fetch → score → generate → push to review queue. Heaviest phase.

### Tools to implement (`tools/content.py`)

**Fetching (3 tools)**
1. `fetch_rss_feed(url, since)` — feedparser → list of `{title, url, published, text_snippet}`
2. `scrape_website(url)` — httpx + BeautifulSoup → article text
3. `check_url_used(channel_id, url)` — check `content_items` table (dedup)

**Scoring (2 tools)**
4. `score_content_items(items[], channel_dna, strategy, competitor_posts[])` — 7-signal scorer:
   - **Relevance**: keyword overlap with `channel_dna.topics` → Jaccard ≥ 0.3
   - **Freshness**: age < 48h = 1.0, decay = max(0, 1 − age_hrs/48)
   - **Novelty**: Jaccard similarity to last 30 posts < 0.3
   - **Goal Alignment**: topic in `strategy.focus_topics`
   - **Virality**: question mark / list / "How" / "Why" in title → 1.0
   - **Competitor Set**: not in last 7d competitor posts (Jaccard)
   - **Brand Safety**: blocklist keyword check → 0 if flagged
   - Return: `green_count`, `signals_dict`, `total_score`
5. `update_source_quality_score(source_id, passed)` — EMA update:
   ```
   new_score = 0.1 × passed + 0.9 × old_score
   ```
   Deactivate source if `avg < 2.5` after 20 items.

**Generation (2 LLM tools)**
6. `generate_post(item, channel_dna, strategy)` — Claude API call (tool_use), Telegram-native format
7. `generate_original_post(topic, channel_dna, strategy)` — fallback when no source passes scoring

**Queue (3 tools)**
8. `add_to_review_queue(channel_id, post_dict, slot_time)` — insert `generated_posts` + `post_queue`
9. `get_review_queue(channel_id)` — fetch pending items
10. `update_review_status(post_id, status, edited_text?)` — approve/edit/reject

**Publishing (2 tools)**
11. `publish_post(channel_username, post_text, media?)` — `send_message` via Bot API
12. `reschedule_post(post_id, new_slot_time)` — update `post_queue`

### Slot trigger logic
```python
# APScheduler fires this per slot
async def content_slot_job(channel_id, slot_time, topic_hint):
    items = await fetch_all_sources(channel_id)
    scored = await score_content_items(items, ...)
    top = [i for i in scored if i.green_count >= 4]
    if top:
        post = await generate_post(top[0], ...)
    else:
        post = await generate_original_post(topic_hint, ...)
    await add_to_review_queue(channel_id, post, slot_time)
```

### Deliverable
`python -m agents.content_intelligence --channel @techdigest_in --slot "2026-06-23T20:00"` adds 1 item to review queue. Approve it → published to channel.

---

## Phase 7 — Review Queue (Telegram Bot) (Days 34–38)

**Goal:** Operator reviews posts from Telegram itself (inline keyboard). No web UI required to approve.

### Bot conversation flow
```
Bot → sends post text + score summary
      [✅ Approve] [✏️ Edit] [❌ Reject]

✅ Approve → publish_post() → confirm message
✏️ Edit    → "Send your edited version:" → receive text → re-score → re-queue
❌ Reject  → update_review_status(rejected) → penalise source score
```

### Implementation
- Handler: `python-telegram-bot` `CallbackQueryHandler`
- Notifications: bot pushes to admin user `ADMIN_TELEGRAM_ID` on new queue item
- All state in `post_queue.status` column (no in-memory state)

### Deliverable
End-to-end flow: content slot fires → Telegram bot sends message with inline keyboard → approve → message published to channel.

---

## Phase 8 — Scheduler & Orchestration (Days 39–42)

**Goal:** Everything runs automatically on cron.

### APScheduler jobs
```python
scheduler.add_job(daily_analytics_strategy, 'cron', hour=2)         # 02:00 UTC daily
scheduler.add_job(weekly_full_cycle,         'cron', day_of_week=0)  # Mon 03:00 UTC
scheduler.add_job(content_slot_dispatcher,   'cron', ...)            # dynamic, from cron_jobs table
scheduler.add_job(monthly_full_audit,        'cron', day=1, hour=4)  # 1st of month
```

### `weekly_full_cycle` sequence
```
channel_dna_agent.run()
competitor_intelligence_agent.run()
analytics_agent.run()
          ↓ all done?
strategy_agent.run()
          ↓ done?
update_cron_for_content_agent()  # reschedules content slots
```

### Deliverable
`python -m scheduler.main` starts all jobs. Logs show correct fire times. Missed jobs handled by `misfire_grace_time=600`.

---

## Phase 9 — Web UI (Days 43–50)

**Goal:** Dashboard we designed — Next.js, connects to FastAPI backend.

### FastAPI endpoints to build
```
GET  /api/channels/{id}/dashboard    ← KPIs, today's timeline
GET  /api/channels/{id}/queue        ← review queue items
POST /api/channels/{id}/queue/{post_id}/approve
POST /api/channels/{id}/queue/{post_id}/reject
PUT  /api/channels/{id}/queue/{post_id}    ← edit text
GET  /api/channels/{id}/analytics    ← snapshots, growth chart
GET  /api/channels/{id}/strategy     ← active strategy + slots
GET  /api/channels/{id}/competitors  ← ranked list
POST /api/channels/{id}/agents/run   ← manual trigger
```

### UI screens (already designed)
1. Dashboard — KPIs, timeline, insights
2. Review queue — approve/edit/reject
3. Analytics — growth chart, ER by format
4. Strategy — content mix, slot list
5. Competitors — ranked table

### Deliverable
`npm run dev` shows dashboard populated with real DB data. All approve/reject actions call real API.

---

## Phase 10 — Testing & Hardening (Days 51–55)

### Test coverage targets
- Unit tests: all formula functions (ER, churn signal, 7-signal scorer, rank formula)
- Integration tests: each agent end-to-end against a real test channel
- E2E test: full weekly cycle on a dummy channel

### Edge cases to handle
- Channel has 0 posts → skip scoring, log warning
- TGStat / Telemetr API down → continue with partial data, log fallback used
- All 7 signals fail → `generate_original_post` (fallback LLM)
- Disappearing messages on → `has_disappearing_messages=True`, rank penalty applied
- Claude API rate limit → exponential backoff (max 3 retries)
- Post slot fires but queue item already approved → skip silently

### Monitoring
- `agent_runs` table is the audit log — query for failures
- Sentry DSN for uncaught exceptions
- Telegram alert bot for failed agent runs

---

## Team Split (2 devs)

| Dev A | Dev B |
|---|---|
| DB models, shared tools, Channel DNA, Analytics | Competitor Intelligence, Strategy, Content Intel |
| Scheduler + orchestration | Review queue bot + publisher |
| FastAPI backend | Next.js UI |

---

## First 3 Things to Build (Start Tomorrow)

1. `docker-compose.yml` with Postgres + Redis
2. `db/models.py` — all 14 tables as SQLAlchemy models
3. `tools/shared.py` — `get_telegram_channel_info` + `get_channel_posts` (verify with a real @channel)

Once Step 3 works you have your data pipeline foundation and all other agents can be built on top.