# Telegram Growth Agent — Dashboard (Next.js 14)

5-screen operator dashboard that consumes the FastAPI backend.

## Prerequisites
- **Node.js 18+** (install from https://nodejs.org)
- The FastAPI backend running: `uvicorn api.main:app --port 8000`

## Setup
```bash
cd ui
cp .env.local.example .env.local      # points at http://localhost:8000
npm install
npm run dev                           # http://localhost:3000
```

## Screens
| Route | Screen |
|---|---|
| `/` | Channel list + onboard form |
| `/channels/{id}` | Dashboard — KPIs, insights, today's timeline |
| `/channels/{id}/queue` | Review queue — approve / edit / reject |
| `/channels/{id}/analytics` | Growth + ER charts, snapshot table |
| `/channels/{id}/strategy` | Content mix, focus topics, tactics, post slots |
| `/channels/{id}/competitors` | Ranked competitor table |

The per-channel page has **Run agent** buttons (onboard / dna / competitor /
analytics / strategy) that call `POST /api/channels/{id}/agents/run`.

## Notes
- CORS is pre-allowed for `localhost:3000` in the backend.
- Approve only marks status; publishing is deferred until `BOT_TOKEN` is set.
