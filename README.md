# Telegram Growth & Retention Agent - Data Collection Layer

Production-ready data collection pipeline for Telegram channels. Collects posts, subscriber counts, and metadata into a structured database for downstream AI analysis.

## Architecture

```
app/
  config/       - Pydantic settings & constants
  telegram/     - Telethon client, auth, channel resolver, data fetcher
  database/     - SQLAlchemy ORM models, repositories, async engine
  services/     - Business logic for data collection & validation
  utils/        - Logging, custom exceptions, helpers
main.py         - CLI entry point
```

## Setup

1. Clone and install dependencies:

```bash
cd telegram-growth-agent
pip install -r requirements.txt
```

2. Get Telegram API credentials:
   - Visit https://my.telegram.org/apps
   - Create an app to get `API_ID` and `API_HASH`

3. Configure environment:

```bash
cp .env.example .env
# Edit .env with your API_ID, API_HASH, PHONE_NUMBER, and DATABASE_URL
```

## Usage

```bash
python -m app.main --channel @grabonindia
```

Scheduler and channel registry commands are also available from the repository root:

```bash
python main.py register --channel @grabonindia
python main.py unregister --channel @grabonindia
python main.py list
python main.py run-once
python main.py schedule
python main.py analyze --channel @grabonindia
python main.py analyze-registered
```

AI prompt execution requires an OpenAI API key in your environment:

```bash
setx OPENAI_API_KEY "your_api_key"
```

On first run, you'll be prompted for the OTP code sent to your Telegram account. The session is saved for reuse.

## Pipeline Flow

1. Authenticate with Telegram (OTP on first run, session reuse thereafter)
2. Resolve channel by username
3. Fetch latest 500 posts (in batches of 100, with FloodWait handling)
4. Fetch subscriber count (daily snapshot with upsert)
5. Fetch channel metadata (title, description, creation date, etc.)
6. Store all data in SQLite database via SQLAlchemy ORM
7. Run validation checks
8. Print summary report

## Database Schema

- `channels` - Channel metadata (title, username, description, etc.)
- `posts` - Individual channel posts with views, forwards, reactions
- `subscriber_snapshots` - Daily subscriber count snapshots

## Future-Proof Design

The repository pattern and clean layering allow downstream modules (growth scoring, retention analysis, competitor benchmarking, recommendations) to consume stored data directly without re-fetching from Telegram.
