#!/bin/sh
# Container entrypoint for the API service.
# Runs DB migrations, then hands off to uvicorn via exec so uvicorn becomes PID 1
# (the container stays alive as long as the server runs, and signals propagate).
set -e

echo "=== [start.sh] applying migrations (alembic upgrade head) ==="
python -m alembic upgrade head
echo "=== [start.sh] migrations done ==="

PORT="${PORT:-8000}"
echo "=== [start.sh] starting uvicorn on 0.0.0.0:${PORT} ==="
exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT}"
