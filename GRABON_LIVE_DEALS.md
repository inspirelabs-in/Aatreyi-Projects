# GrabOn Live Deals — branch `grabon-live-deals`

Automates the manual workflow: scrape **today's** Amazon India + Flipkart product
deals → wrap in affiliate links → feed into GrabOn's content generation → review/post.

## What it does
- `tools/deal_scrapers.py` — Playwright (headless Chromium) scrapers for Amazon &
  Flipkart across **14 categories** (electronics, mobiles, fashion men/women,
  footwear, home & kitchen, home decor, appliances, beauty, sports, watches, bags,
  toys, grocery).
- **Discount policy:** prefer deals **≥80% off**; if none, fall back but **never
  below 65%**. (Scrapes the 60%+ pool, filters in Python.)
- **Affiliate links:** Amazon → `?tag=<AMAZON_AFFILIATE_TAG>` (default `tlg022-21`);
  Flipkart → raw unless `FLIPKART_AFFILIATE_TAG` is set.
- **Today's deals only:** scrapes current results sorted by discount; the content
  agent's existing URL de-dup prevents reposting.
- **Integration:** for deals-category channels the content agent tries live deals
  first (`_fetch_live_deals`), then falls back to **grabon.in coupon pages**
  (`scrape_deal_links`) if live scraping returns nothing.
- **Daily scheduler:** new `daily_deals` job (`scheduler/jobs.run_daily_deals`)
  runs every day at `DEAL_REFRESH_HOUR` (default 08:00 IST) — fresh plan + content
  from today's deals for every deals channel.

## Config (env vars / `.env`)
| Var | Default | Meaning |
|---|---|---|
| `AMAZON_AFFILIATE_TAG` | `tlg022-21` | appended to Amazon links |
| `FLIPKART_AFFILIATE_TAG` | _(blank)_ | set when the team provides one |
| `DEAL_PREFERRED_DISCOUNT` | `80` | preferred minimum discount % |
| `DEAL_MIN_DISCOUNT` | `65` | hard floor — never post below this |
| `DEAL_PLATFORMS` | `Amazon,Flipkart` | which platforms to scrape |
| `DEAL_MAX_PER_CATEGORY` | `3` | deals kept per category |
| `DEAL_REFRESH_HOUR` | `8` | IST hour for the daily deals job |

## ⚠️ Deployment reality — read before deploying
1. **Image weight:** Playwright Chromium adds **~400MB** to the Docker image and
   slows builds. Installed via `python -m playwright install --with-deps chromium`
   in the Dockerfile.
2. **Datacenter IPs get blocked.** Amazon/Flipkart actively block headless browsers
   from cloud/datacenter IPs (Railway included). From a **residential IP** (your
   laptop) the scrapers work — that's why the manual workflow worked. On Railway
   they will likely return **nothing or a captcha**, and the pipeline will **fall
   back to grabon.in coupon pages** automatically (still affiliate-linked, still
   on-brand, just brand-landing pages rather than specific products).
   - To get real product-level deals in production you'll eventually want one of:
     a residential/rotating proxy for Playwright, OR the official **Amazon PA-API /
     Flipkart affiliate API**, OR run the scraper on a residential box and push
     deals into the DB. (Tracked in the integration MD: grbn.in shortener + Flipkart
     tag + Myntra/Nykaa creds pending from the tech team.)
3. **Myntra/Nykaa** block headless browsers entirely — covered by the grabon.in
   fallback (`grabon.in/myntra-coupons/`, etc.).

## Deploy
This is a **separate Railway service/branch decision**. To deploy this branch:
- Point Railway at `grabon-live-deals` (or merge to the deploy branch), then
  `railway up --service api`. The Dockerfile installs Chromium automatically.
- Set `FLIPKART_AFFILIATE_TAG` (and any proxy creds) in Railway Variables when available.
