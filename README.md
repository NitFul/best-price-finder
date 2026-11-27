# Best Price Finder

Type an item name and get store options ranked by **effective price**
(price + shipping − Rakuten cash back).

## Setup (one time)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and paste your free key from https://serper.dev after `SERPER_API_KEY=`.

## Run

```powershell
.\.venv\Scripts\streamlit run app.py
```

Your browser opens at http://localhost:8501. Without a key, the app runs in
**demo mode** with made-up prices.

## Amazon prices (optional)

Amazon rarely appears in Google Shopping. To include Amazon listings with
real prices, get a free key at https://serpapi.com (250 searches/month) and
add `SERPAPI_KEY=...` to `.env`. Without it, the app still shows a link to
the Amazon product page. `AMAZON_DAILY_LIMIT` (default 8) keeps you within
the free plan.

## Costco prices (optional)

Costco isn't in Google Shopping and has no public API. With `APIFY_TOKEN`
set, the app runs the Apify actor `sian.agency/costco-data-scraper` in the
background (usually under a minute; the page updates when it's done). This
scrapes costco.com, which Costco's terms don't allow. It costs about $0.10
per search (Apify's free $5/month covers ~50), and is capped by
`COSTCO_DAILY_LIMIT` (default 2), $0.15 per run, and the monthly free credit. Without a token, the
app shows a link to the Costco product page.

## Cashback rates

Rates live in `cashback_rates.csv`. To refresh them from Rakuten (read from
Google search results for Rakuten's store pages, 1 search credit per store):

- Automatically: the top 3 stores of each search are looked up if not saved yet, or
- From the terminal: `.\.venv\Scripts\python update_rates.py` (or list store names
  to update only those).

You can also edit the file by hand. Then commit and push
`cashback_rates.csv` to update the public site.

## Free limits

Each new search uses 1 Serper credit (about 2,500 free). The same search
within an hour is cached and doesn't use a credit.

## Tests

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
```

## Public website (Streamlit Community Cloud, free)

1. Sign in at https://share.streamlit.io with GitHub.
2. **Create app**, then pick this repo, branch `main`, file `app.py`.
3. Under **Advanced settings**, choose Python 3.12 and paste into **Secrets**:
   ```toml
   SERPER_API_KEY = "your-key"
   SERPAPI_KEY = "your-serpapi-key"   # optional, for Amazon prices
   AMAZON_DAILY_LIMIT = "8"
   DAILY_SEARCH_LIMIT = "60"
   SESSION_SEARCH_LIMIT = "10"
   ```
   Don't set `ALLOW_RATE_EDITING` there, so visitors can't change rates.
4. **Deploy.**

To update cashback rates on the public site: edit them locally, then commit
and push `cashback_rates.csv`. The site redeploys automatically.

**Secrets:** the real key lives only in `.env` (ignored by Git) and in the
Streamlit Secrets box. Never put it in a committed file.
