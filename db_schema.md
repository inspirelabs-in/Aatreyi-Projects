# Telegram Growth & Retention Agent — DB Schemas & I/O Models

---

## Schema Map (Entity Relationships)

```
channels ──────────────────────────────────────────────────────────────┐
    │                                                                   │
    ├──► channel_dna          (1:1)  Tier B/C profile                  │
    ├──► competitors           (1:N)  discovered rival channels         │
    │        └──► competitor_posts  (1:N)  their top posts             │
    ├──► analytics_snapshots  (1:N)  daily / weekly metrics            │
    ├──► strategies            (1:N)  generated action plans            │
    │        └──► strategy_tasks    (1:N)  per-day post slots          │
    ├──► content_sources       (1:N)  RSS, websites, scrapers           │
    │        └──► content_items     (1:N)  raw sourced articles        │
    │                 └──► content_scores   (1:1)  7-signal score      │
    ├──► generated_posts       (1:N)  LLM-generated Telegram posts      │
    │        └──► post_queue         (1:1)  scheduling record           │
    └──► agent_runs            (1:N)  audit log per agent execution    ─┘
```

---

## 1. Onboarding

### Table: `channels`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | Unique channel identifier |
| `telegram_username` | VARCHAR(64) UNIQUE | e.g. `@mynewschannel` |
| `telegram_id` | BIGINT | Resolved Telegram channel ID |
| `display_name` | VARCHAR(128) | Channel title |
| `tier` | ENUM(`new`, `mid`, `established`) | Growth tier |
| `category` | VARCHAR(64) | Primary niche e.g. `crypto`, `tech` |
| `sub_category` | VARCHAR(64) | Narrower niche (auto or manual) |
| `growth_goal` | VARCHAR(256) | User-stated goal |
| `language` | VARCHAR(8) | `en`, `hi`, etc. |
| `status` | ENUM(`onboarding`, `active`, `paused`) | Current state |
| `created_at` | TIMESTAMP | |
| `updated_at` | TIMESTAMP | |

**INPUT**
```
{
  telegram_username : "@mychannel",
  category          : "tech",
  growth_goal       : "reach 10k in 3 months",
  language          : "en",
  tier              : "new"          // determined by subscriber count
}
```

**OUTPUT**
```
{
  channel_id   : "uuid",
  tier         : "new",
  status       : "onboarding",
  next_step    : "competitor_intelligence"
}
```

---

## 2. Channel DNA Agent  *(Tier B/C only)*

### Table: `channel_dna`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `subscriber_count` | INT | Current subscribers |
| `avg_views_per_post` | FLOAT | Rolling 30-day average |
| `avg_er` | FLOAT | Engagement rate % |
| `post_frequency_per_day` | FLOAT | Average posts/day |
| `best_post_hour` | SMALLINT | 0–23 UTC hour with highest ER |
| `best_post_days` | JSONB | `["Mon","Wed","Fri"]` |
| `top_content_formats` | JSONB | `[{"format":"poll","share":0.4}, ...]` |
| `tone_fingerprint` | JSONB | `{"formal":0.2,"casual":0.7,"humorous":0.1}` |
| `audience_geo_top3` | JSONB | `[{"country":"IN","pct":0.6}, ...]` |
| `growth_curve` | JSONB | `[{"date":"2024-01","subs":3200}, ...]` |
| `category` | VARCHAR(64) | Auto-detected niche |
| `sub_category` | VARCHAR(64) | Auto-detected sub-niche |
| `analysed_at` | TIMESTAMP | Last DNA refresh |

**INPUT**
```
{
  channel_id       : "uuid",
  telegram_username: "@mychannel"
}
// Telegram Bot API pulls: getChatHistory, getChatMemberCount,
// message reactions, forwards, views per post (last 90 days)
```

**OUTPUT**
```
{
  channel_id          : "uuid",
  subscriber_count    : 18400,
  avg_er              : 6.2,
  best_post_hour      : 18,
  best_post_days      : ["Tue","Thu","Sat"],
  top_content_formats : [{"format":"article","share":0.5},{"format":"poll","share":0.3}],
  tone_fingerprint    : {"casual":0.65,"formal":0.25,"humorous":0.10},
  category            : "personal-finance",
  analysed_at         : "2024-11-01T10:00:00Z"
}
```

---

## 3. Competitor Intelligence

### Table: `competitors`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | Parent channel being managed |
| `competitor_username` | VARCHAR(64) | Rival channel handle |
| `competitor_tg_id` | BIGINT | Telegram ID |
| `display_name` | VARCHAR(128) | |
| `subscriber_count` | INT | At time of discovery |
| `post_frequency_per_day` | FLOAT | |
| `avg_er` | FLOAT | Engagement rate |
| `top_content_themes` | JSONB | `["AI tools","startup news"]` |
| `source` | ENUM(`telegram_api`,`tgstat`,`telemetr`,`duckduckgo`) | Discovery source |
| `rank` | SMALLINT | Rank by relevance score |
| `discovered_at` | TIMESTAMP | |
| `refreshed_at` | TIMESTAMP | |

### Table: `competitor_posts`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `competitor_id` | UUID FK → competitors | |
| `telegram_message_id` | BIGINT | |
| `text_preview` | TEXT | First 500 chars |
| `format` | ENUM(`text`,`photo`,`video`,`poll`,`link`) | |
| `views` | INT | |
| `forwards` | INT | |
| `reactions_count` | INT | |
| `er` | FLOAT | Computed ER |
| `posted_at` | TIMESTAMP | |

**INPUT**
```
{
  channel_id : "uuid",
  category   : "tech",
  keywords   : ["AI news","startup India"],
  limit      : 10              // top N competitors to fetch
}
// Query order: DuckDuckGo → Telegram Bot API → TGStat → Telemetr
```

**OUTPUT**
```
{
  channel_id  : "uuid",
  competitors : [
    {
      username          : "@techbulletin",
      subscriber_count  : 45000,
      post_freq_per_day : 3.2,
      avg_er            : 5.8,
      top_themes        : ["AI","SaaS","funding"],
      rank              : 1,
      source            : "telegram_api"
    },
    ...
  ],
  total_found : 10,
  refreshed_at: "2024-11-01T10:05:00Z"
}
```

---

## 4. Analytics Agent

### Table: `analytics_snapshots`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `snapshot_type` | ENUM(`daily`,`weekly`,`monthly`) | |
| `period_start` | DATE | |
| `period_end` | DATE | |
| `subscriber_count` | INT | Snapshot value |
| `subscriber_delta` | INT | Change from previous period |
| `subscriber_delta_pct` | FLOAT | % change |
| `avg_views` | FLOAT | Avg views per post this period |
| `avg_er` | FLOAT | Avg ER this period |
| `total_posts` | SMALLINT | Posts published |
| `top_post_id` | UUID FK → generated_posts | Best-performing post |
| `reach` | INT | Estimated unique reach |
| `churn_signal` | BOOLEAN | True if unsubscribes spike > 2× |
| `churn_rate` | FLOAT | % subscriber loss |
| `insights` | JSONB | `[{"type":"drop","note":"ER fell 30% vs last week"}]` |
| `created_at` | TIMESTAMP | |

**INPUT**
```
{
  channel_id    : "uuid",
  snapshot_type : "daily",
  period_start  : "2024-11-01",
  period_end    : "2024-11-01"
}
// Pulls from: Telegram Bot API (getChatMemberCount, message stats),
// previous analytics_snapshots for delta computation
```

**OUTPUT**
```
{
  channel_id         : "uuid",
  snapshot_type      : "daily",
  subscriber_count   : 18540,
  subscriber_delta   : +120,
  subscriber_delta_pct: +0.65,
  avg_views          : 3200,
  avg_er             : 6.4,
  total_posts        : 3,
  churn_signal       : false,
  insights           : [
    {"type":"growth","note":"Best single-day gain this month"},
    {"type":"format","note":"Polls outperforming articles 2×"}
  ]
}
```

---

## 5. Strategy Agent

### Table: `strategies`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `strategy_type` | ENUM(`daily`,`weekly`,`monthly`) | |
| `period_start` | DATE | |
| `period_end` | DATE | |
| `goal` | TEXT | e.g. "Gain 500 subscribers this week" |
| `post_frequency_per_day` | FLOAT | Recommended posts/day |
| `content_mix` | JSONB | `[{"format":"article","pct":50},{"format":"poll","pct":30},{"format":"meme","pct":20}]` |
| `primary_topics` | JSONB | `["AI tools","productivity"]` |
| `growth_tactics` | JSONB | `[{"tactic":"cross_post","detail":"partner with @channel2"}]` |
| `status` | ENUM(`draft`,`active`,`completed`) | |
| `created_at` | TIMESTAMP | |

### Table: `strategy_tasks`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `strategy_id` | UUID FK → strategies | |
| `channel_id` | UUID FK → channels | |
| `scheduled_date` | DATE | Target publish date |
| `scheduled_time` | TIME | UTC post slot |
| `format` | ENUM(`text`,`photo`,`video`,`poll`,`link`,`carousel`) | |
| `topic` | VARCHAR(128) | Content topic for this slot |
| `content_item_id` | UUID FK → content_items NULL | Linked after content agent runs |
| `generated_post_id` | UUID FK → generated_posts NULL | Linked after generation |
| `status` | ENUM(`pending`,`content_sourced`,`generated`,`approved`,`published`,`rejected`) | |

**INPUT**
```
{
  channel_id     : "uuid",
  strategy_type  : "weekly",
  period_start   : "2024-11-04",
  period_end     : "2024-11-10",
  analytics      : { /* latest analytics_snapshot */ },
  channel_dna    : { /* channel_dna record */ },
  competitors    : [ /* top 5 competitor records */ ]
}
```

**OUTPUT**
```
{
  strategy_id          : "uuid",
  post_frequency_per_day: 3,
  content_mix          : [
    {"format":"article","pct":50},
    {"format":"poll","pct":30},
    {"format":"meme","pct":20}
  ],
  primary_topics       : ["AI tools","startup funding"],
  tasks                : [
    {"date":"2024-11-04","time":"09:00","format":"article","topic":"AI tools roundup"},
    {"date":"2024-11-04","time":"17:00","format":"poll","topic":"audience opinion on LLMs"},
    {"date":"2024-11-04","time":"20:00","format":"meme","topic":"startup life humor"},
    ...
  ]
}
```

---

## 6. Content Intelligence

### Table: `content_sources`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `type` | ENUM(`rss`,`website`,`telegram_channel`,`keyword_db`) | |
| `url` | TEXT | Feed or page URL |
| `name` | VARCHAR(128) | Source label |
| `category` | VARCHAR(64) | Niche tag |
| `fetch_interval_mins` | INT | How often to poll |
| `last_fetched_at` | TIMESTAMP | |
| `is_active` | BOOLEAN | |
| `avg_quality_score` | FLOAT | Rolling average of items from this source |

### Table: `content_items`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `source_id` | UUID FK → content_sources | |
| `external_url` | TEXT | Original article / post URL |
| `title` | VARCHAR(512) | |
| `body_text` | TEXT | Extracted body |
| `author` | VARCHAR(128) | |
| `published_at` | TIMESTAMP | Source publish time |
| `fetched_at` | TIMESTAMP | When agent pulled it |
| `format_tag` | VARCHAR(32) | `article`, `video`, `tweet` etc. |
| `topics` | JSONB | `["AI","productivity"]` |
| `status` | ENUM(`raw`,`scored`,`used`,`dropped`) | |

### Table: `content_scores`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `content_item_id` | UUID FK → content_items | |
| `channel_id` | UUID FK → channels | |
| `relevance` | SMALLINT | 0 or 1 |
| `freshness` | SMALLINT | 0 or 1 |
| `novelty` | SMALLINT | 0 or 1 |
| `goal_alignment` | SMALLINT | 0 or 1 |
| `virality` | SMALLINT | 0 or 1 |
| `competitor_set` | SMALLINT | 0 or 1 |
| `brand_safety` | SMALLINT | 0 or 1 |
| `total_score` | SMALLINT | Sum 0–7 |
| `passed` | BOOLEAN | total_score ≥ threshold |
| `threshold_used` | SMALLINT | Config at time of scoring |
| `scored_at` | TIMESTAMP | |

### Table: `generated_posts`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `content_item_id` | UUID FK → content_items NULL | Source item (null for original posts) |
| `strategy_task_id` | UUID FK → strategy_tasks | Linked slot |
| `post_text` | TEXT | Final Telegram post body |
| `post_format` | ENUM(`text`,`photo`,`video`,`poll`,`link`) | |
| `media_url` | TEXT NULL | If photo/video |
| `cta` | VARCHAR(256) | Call-to-action text |
| `hashtags` | JSONB | `["#AI","#tech"]` |
| `llm_model` | VARCHAR(64) | Model used for generation |
| `generation_prompt` | TEXT | Prompt sent to LLM |
| `review_status` | ENUM(`pending`,`approved`,`edited`,`rejected`) | User decision |
| `edited_text` | TEXT NULL | User-edited version |
| `rejection_reason` | VARCHAR(256) NULL | If rejected |
| `created_at` | TIMESTAMP | |

### Table: `post_queue`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `generated_post_id` | UUID FK → generated_posts | |
| `strategy_task_id` | UUID FK → strategy_tasks | |
| `scheduled_at` | TIMESTAMP | Planned publish time (UTC) |
| `published_at` | TIMESTAMP NULL | Actual publish time |
| `telegram_message_id` | BIGINT NULL | Returned by Telegram after send |
| `status` | ENUM(`queued`,`sent`,`failed`,`skipped`) | |
| `retry_count` | SMALLINT | |
| `error_log` | TEXT NULL | On failure |

**INPUT — Content Intelligence**
```
{
  channel_id       : "uuid",
  strategy_task_id : "uuid",
  strategy         : { format: "article", topic: "AI tools roundup" },
  channel_dna      : { tone_fingerprint: {...}, category: "tech" },
  competitors      : [ /* top posts from competitor_posts */ ],
  sources          : [ /* active content_sources for this channel */ ]
}
```

**OUTPUT — Scored Item**
```
{
  content_item_id : "uuid",
  title           : "10 AI tools reshaping productivity in 2024",
  external_url    : "https://techcrunch.com/...",
  scores          : {
    relevance      : 1,
    freshness      : 1,
    novelty        : 1,
    goal_alignment : 1,
    virality       : 1,
    competitor_set : 0,
    brand_safety   : 1,
    total          : 6,
    passed         : true
  }
}
```

**OUTPUT — Generated Post**
```
{
  generated_post_id : "uuid",
  post_text         : "🔧 10 AI tools you probably haven't tried yet...\n\nFrom Notion AI to Perplexity — here's what's actually saving teams hours every week.\n\n👇 Which one do you use?",
  format            : "text",
  cta               : "👇 Which one do you use?",
  hashtags          : ["#AItools","#productivity","#tech"],
  review_status     : "pending"
}
```

---

## 7. Agent Runs (Audit Log)

### Table: `agent_runs`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `agent` | ENUM(`channel_dna`,`competitor_intelligence`,`analytics`,`strategy`,`content_intelligence`) | |
| `trigger` | ENUM(`cron_daily`,`cron_weekly`,`cron_monthly`,`post_slot`,`manual`) | What fired it |
| `status` | ENUM(`running`,`completed`,`failed`) | |
| `input_snapshot` | JSONB | Input payload (sanitised) |
| `output_summary` | JSONB | Key output metrics |
| `duration_ms` | INT | Execution time |
| `error` | TEXT NULL | If failed |
| `started_at` | TIMESTAMP | |
| `finished_at` | TIMESTAMP | |

---

## 8. Cron Jobs Registry

### Table: `cron_jobs`

| Column | Type | Description |
|---|---|---|
| `id` | UUID PK | |
| `channel_id` | UUID FK → channels | |
| `agent` | ENUM (same as agent_runs.agent) | |
| `cron_expression` | VARCHAR(32) | e.g. `0 9 * * *` |
| `cadence_label` | ENUM(`daily`,`weekly`,`monthly`,`post_slot`,`custom`) | |
| `next_run_at` | TIMESTAMP | |
| `last_run_at` | TIMESTAMP NULL | |
| `last_agent_run_id` | UUID FK → agent_runs NULL | |
| `is_active` | BOOLEAN | |
| `created_at` | TIMESTAMP | |

---

## Full Input → Output Chain

```
ONBOARDING
  IN  : username, category, goal, language
  OUT : channel_id, tier, next_step
        └─────────────────────────────────────────────────────────────────►
                                                                CHANNEL DNA (Tier B/C)
                                                                  IN  : channel_id
                                                                  OUT : dna record (ER, tone, formats, category)
                                                                        │
COMPETITOR INTELLIGENCE ◄───────────────────────────────────────────────┘
  IN  : channel_id, category, keywords
  OUT : ranked competitor list + top posts
        │
        ▼
ANALYTICS AGENT
  IN  : channel_id, snapshot_type, previous snapshots
  OUT : growth delta, ER, churn_signal, insights
        │
        ▼
STRATEGY AGENT
  IN  : channel_id, analytics, dna, competitors
  OUT : strategy + strategy_tasks (post slots per day)
        │
        ▼
CONTENT INTELLIGENCE  ← triggered per post_slot cron
  IN  : strategy_task (format, topic), dna (tone), sources
  OUT : scored content_item → generated_post → review queue
                                                    │
                                         ┌──────────┼──────────┐
                                         ▼          ▼          ▼
                                      Approve     Edit       Reject
                                         │          │
                                         └────┬─────┘
                                              ▼
                                         post_queue → Telegram Publish
```