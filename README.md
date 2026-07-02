# Telegram Growth & Retention Agent

Autonomous multi-agent system that profiles a Telegram channel, scouts competitors,
tracks analytics, plans a posting strategy, and sources/generates posts for review!!

See the design docs at the repo root:
[workflow.md](workflow.md) · [db_schema.md](db_schema.md) · [formulae.md](formulae.md) ·
[prompts_&_tools.md](prompts_&_tools.md) · [implementation_roadmap.md](implementation_roadmap.md)

## Layout

```
agents/      one file per agent (channel_dna, competitor_intelligence, analytics, strategy, content_intelligence)
tools/       tool implementations (shared.py + one module per agent)
db/          SQLAlchemy models + Alembic migrations
scheduler/   APScheduler cron jobs
api/         FastAPI app (webhooks + UI backend)
ui/          Next.js dashboard
tests/       pytest suite
config.py    env-var settings (single source)
```

## Local setup (Phase 0)

```bash
# 1. Python deps (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. Env
cp .env.example .env            # then fill in real credentials

# 3. Datastores (local dev — just DB + Redis)
docker compose up -d db redis  # Postgres :5433->5432 + Redis :6379

# 4. Migrations
alembic upgrade head            # applies the baseline (empty until Phase 1)

# 5. Sanity check
python -c "from config import settings; print(settings.model_dump())"
```

## Telegram access (one-time login)

The agents read channel data via Telethon (MTProto), which needs a one-time
interactive login. If your network blocks Telegram (ISP/DPI), route around it:

```bash
# Optional: if direct connection is blocked, find + set a working MTProxy
python -m tools.find_proxy --write        # writes TELEGRAM_PROXY into .env
# (or connect a VPN and leave TELEGRAM_PROXY empty)

# One-time login — enter the code Telegram sends to your phone
python -m tools.login

# Verify
python -m pytest tests/test_shared_tools.py -v
```

If Telegram stops connecting later, the proxy likely died — re-run
`python -m tools.find_proxy --write` to grab a fresh one.

## Tier-aware workflow

Each channel follows a pipeline chosen by its tier (auto-classified from
subscriber count, refreshed weekly — a channel graduates automatically at 5k):

| Tier | Subscribers | Pipeline |
|---|---|---|
| **A** (new, no history) | < 5,000 & < 10 recent posts | Competitor → Strategy → Content *(lean)* |
| **A** (new, posting) | < 5,000 & ≥ 10 recent posts | DNA → Competitor → Analytics → Strategy → Content *(full)* |
| **B/C** (mid/established) | ≥ 5,000 | DNA → Competitor → Analytics → Strategy → Content *(full)* |

Routing keys on **data availability**, not just subscriber count: a brand-new
channel starts lean, then **DNA + Analytics switch on automatically once it has
enough post history** (weekly cycle re-checks; daily keys off a valid DNA
profile). A Tier-A channel also graduates to B/C automatically at 5k subs.

Onboard a channel (runs the tier-appropriate initial pipeline):
```bash
python -m scheduler.onboard --channel @mychannel --category deals
```
Or via API: `POST /api/channels/{id}/agents/run` with `{"agent": "onboard"}`.

Category detection is generic (keyword rules across deals, tech, crypto,
finance, news, sports, education, health, gaming, business, shopping…); set
`channels.category` explicitly at onboarding to override auto-detection.

### Competitor discovery (brand-centric)
Competitor Intelligence runs **after** DNA (needs the category/brand). It does
**not** keyword-search Telegram directly — instead it:
1. web-searches the channel's **real competitor brands** (LLM extracts names from
   results), e.g. GrabOn → DesiDime, CouponDunia, FreeKaaMaal;
2. finds **each brand's Telegram channel** (web search → t.me handle, TG fallback);
3. resolves + benchmarks them (avg subs/ER/frequency, your ER gap, top competitor);
4. feeds benchmarks + topic gaps to Strategy, which sets targets against them
   (`close_er_gap`, `mirror_format`, cover gap topics).

## Deploy always-on (Docker)

The agent must run 24/7 for cron jobs (daily 07:00 IST cycle, content dispatcher)
to fire — a laptop that sleeps will skip them. Run the always-on parts on any
host (VPS / Railway / Fly.io / Pi) with one command:

```bash
docker compose up -d --build      # db, redis, migrate (once), api, scheduler
docker compose logs -f scheduler  # watch cron fire times (IST)
```

Services (all `restart: unless-stopped`, so they survive reboots):
`db` · `redis` · `migrate` (one-shot `alembic upgrade head`) · `api` (:8000) · `scheduler`.

Notes before deploying to a server:
- **Secrets** come from `.env` (loaded via `env_file`); containers override only
  `DATABASE_URL`/`REDIS_URL` to point at the in-compose `db`/`redis`.
- **Fresh DB**: the container Postgres is separate from your local one — you'll
  re-onboard channels there (or set `DATABASE_URL` to an existing/managed DB).
- **Telegram**: `tga_user.session` is mounted as a volume. On a server Telegram
  usually isn't blocked, so clear `TELEGRAM_PROXY` in `.env`; a new server IP may
  require a one-time re-login (`python -m tools.login` inside the container).
- **UI**: deploy separately (or run locally) and point `NEXT_PUBLIC_API_BASE` at
  the server's `http://<host>:8000`.

## API (UI backend)

```bash
uvicorn api.main:app --reload --port 8000
# docs at http://localhost:8000/docs
```

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness |
| GET | `/api/agent-runs` | audit log (filter `?status=failed`) |
| GET | `/api/channels` | list channels |
| POST | `/api/channels` | onboard a channel |
| GET | `/api/channels/{id}/dashboard` | KPIs + today's timeline + insights |
| GET | `/api/channels/{id}/queue` | pending review posts |
| POST | `/api/channels/{id}/queue/{post}/approve` | approve (publish deferred till BOT_TOKEN) |
| POST | `/api/channels/{id}/queue/{post}/reject` | reject |
| PUT | `/api/channels/{id}/queue/{post}` | edit post text |
| GET | `/api/channels/{id}/analytics` | snapshot history (chart data) |
| GET | `/api/channels/{id}/strategy` | active strategy + slots |
| GET | `/api/channels/{id}/competitors` | ranked competitors |
| POST | `/api/channels/{id}/agents/run` | manually trigger an agent |

## Roadmap status

- [x] Phase 0 — Project setup
- [x] Phase 1 — DB models + shared tools
- [x] Phase 2 — Channel DNA Agent
- [x] Phase 3 — Competitor Intelligence Agent
- [x] Phase 4 — Analytics Agent
- [x] Phase 5 — Strategy Agent
- [x] Phase 6 — Content Intelligence Agent
- [ ] Phase 7 — Review Queue (Telegram bot) — deferred (needs BOT_TOKEN)
- [x] Phase 8 — Scheduler & orchestration
- [x] Phase 9 — Web UI (FastAPI backend + Next.js 14 dashboard — see [ui/](ui/))
- [x] Phase 10 — Testing & hardening (E2E + edge cases + agent-runs audit + optional Sentry)
