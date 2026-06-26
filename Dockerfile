# App image for the Python services (api / scheduler / agents).
# DB + Redis run as their own containers (see docker-compose.yml).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright Chromium + OS deps for live Amazon/Flipkart deal scraping.
# (Heavy: adds ~400MB. Datacenter IPs are often blocked by Amazon/Flipkart —
# the deal pipeline falls back to grabon.in coupon pages when scraping yields
# nothing, so the app still works without a usable browser.)
RUN python -m playwright install --with-deps chromium

COPY . .

CMD ["sh", "start.sh"]
