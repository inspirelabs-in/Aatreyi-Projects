# Telegram Growth & Retention Agent — Architecture

---

## Agent Roster

| Agent | Core Responsibility | Cadence |
|---|---|---|
| **Channel DNA Agent** | Channel profile, metrics, category, audience fingerprint | Weekly |
| **Competitor Intelligence** | Rival channel discovery via Telegram API / TGStat / Telemetr | Weekly |
| **Analytics Agent** | Growth rate, reach, engagement, churn signals | Daily & Weekly |
| **Strategy Agent** | Action plan, posting cadence, content mix | Daily & Weekly |
| **Content Intelligence** | Source → Score → Generate → Review → Publish | Per post-slot |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        👤  USER                                         │
│              Tier A (new)          Tier B/C (mid/established)           │
│        username · category · goal       username only                   │
└───────────────┬────────────────────────────┬───────────────────────────┘
                │                            │
                ▼                            ▼
        ┌───────────────┐          ┌──────────────────────┐
        │  Competitor   │◄─────────│  Channel DNA Agent   │
        │  Intelligence │          │  metrics · niche     │
        │  DDG → TG API │          │  audience · history  │
        │  TGStat/Telemetr         └──────────────────────┘
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  Analytics    │
        │  Agent        │
        │  growth Δ     │
        │  ER · churn   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐
        │  Strategy     │
        │  Agent        │
        │  action plan  │
        │  post slots   │
        └───────┬───────┘
                │
                ▼
        ┌───────────────┐       ┌─────────────────────────┐
        │  Content      │◄──────│  Data Sources           │
        │  Intelligence │       │  • RSS / Atom feeds     │
        │  source       │       │  • Web scrape           │
        │  score        │       │  • Telegram channels    │
        │  generate     │       │  • Topic / keyword DB   │
        └───────┬───────┘       └─────────────────────────┘
                │
                ▼
        ┌────────────────────────────────┐
        │        User Review Queue       │
        │                                │
        │  ✅ Approve → Scheduler        │
        │  ✏️  Edit    → Re-score        │
        │  ❌ Reject  → Penalise source  │
        └────────────────────────────────┘
                │
                ▼
        ┌───────────────┐
        │  📤 Telegram  │
        │    Publish    │
        └───────────────┘
```

---

## Channel Tier Flows

### Tier A — New Channel (0 – 5 000 subscribers)

```
  Onboarding          Competitor        Strategy         Content           Review        Publish
  ─────────────       Intelligence      Agent            Intelligence      Queue
  • username    ────► • DDG search ───► • 30-day    ───► • Source    ───► ✅ Approve ──► 📤
  • category          • TG API          plan             • Classify        ✏️ Edit ──────► re-score
  • niche             • TGStat          • post slots     • Score           ❌ Reject
  • goal              • Telemetr        • content mix    • Generate
```

### Tier B/C — Mid & Established Channel (5 000 + subscribers)

```
  Onboarding     Channel DNA       Competitor     Analytics      Strategy       Content        Review       Publish
  ───────────    Agent             Intelligence   Agent          Agent          Intelligence   Queue
  • username ──► • history   ────► • DDG       ► • growth Δ ──► • action  ───► • source  ───► ✅ Approve ──► 📤
                 • metrics         • TG API       • ER ratio      plan          • score        ✏️ Edit ──────► re-score
                 • niche           • TGStat       • churn        • cadence      • generate     ❌ Reject
                 • audience        • Telemetr     • digest       • mix %
```

---

## Content Scoring Pipeline

```
  Raw Source
  (RSS · Scrape · Telegram · DB)
        │
        ▼
  ┌─────────────┐
  │  Classify   │  topic · format · source authority
  └──────┬──────┘
         │
         ▼
  ┌─────────────────────────────────────────┐
  │           7-Signal Score                │
  │                                         │
  │  1. Relevance      — niche alignment    │
  │  2. Freshness      — < 48 hrs old       │
  │  3. Novelty        — not seen before    │
  │  4. Goal Alignment — matches strategy   │
  │  5. Virality       — shareability       │
  │  6. Competitor Set — not duplicate      │
  │  7. Brand Safety   — no harmful content │
  └──────────────┬──────────────────────────┘
                 │
        ┌────────┴────────┐
        │                 │
   < 4 / 7 green     ≥ 4 / 7 green
        │                 │
        ▼                 ▼
     ❌ Drop         LLM Generate
                   Telegram-native post
                          │
                          ▼
                    Review Queue
```

---

## Cron Schedule

```
  Cadence          Agent(s)                               What runs
  ─────────────────────────────────────────────────────────────────────────
  Every 24 hrs     Strategy Agent, Analytics Agent        Daily plan + metric snapshot
  Every 7 days     Channel DNA, Competitor, Analytics,    Full review cycle
                   Strategy Agent
  Post-slot        Content Intelligence Agent             Triggered per scheduled post time
  Monthly/Custom   All agents                             Full audit + strategy reset
```

