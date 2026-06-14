# Market Lens

A stock market analytics platform that aggregates prices, financials, news, and
sentiment from multiple sources into a single interactive dashboard.

> **Disclaimer:** Educational/informational use only. Not financial advice.

This repo is the **Week 1–3 starter**: a working data pipeline that ingests daily
stock prices and company profiles into a local database. The web app, analytics,
and additional sources get layered on top from here.

---

## Project structure

```
market-lens/
├── README.md
├── requirements.txt
├── .env.example          # copy to .env and fill in (never commit .env)
├── .gitignore
├── config.py             # central config (paths, tickers, db location)
├── db/
│   └── schema.sql        # all CREATE TABLE statements
├── pipeline/
│   ├── db.py             # database connection + schema setup helpers
│   └── ingest_prices.py  # Week 1 job: prices + company profiles
└── data/                 # the SQLite database file lives here (gitignored)
```

## Setup (5 minutes)

You need Python 3.9+ installed. Then, from inside the `market-lens/` folder:

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) copy the env template — not needed for the yfinance starter
cp .env.example .env

# 4. Run the pipeline — creates the database and loads data
python -m pipeline.ingest_prices
```

On the first run it will create `data/market_lens.db`, build the tables, and load
~1 year of daily prices plus profiles for the tickers in `config.py`.

## Verify it worked

```bash
# Peek at the database with the sqlite3 CLI
sqlite3 data/market_lens.db "SELECT ticker, name, sector FROM companies;"
sqlite3 data/market_lens.db "SELECT COUNT(*) FROM stock_prices;"
sqlite3 data/market_lens.db "SELECT job_name, status, rows_added FROM update_logs ORDER BY log_id DESC LIMIT 5;"
```

Or open `data/market_lens.db` in a free GUI like **DB Browser for SQLite**.

## Change which stocks are tracked

Edit the `TICKERS` list in `config.py` and re-run. The job is **idempotent** —
re-running never creates duplicate rows.

## Schedule daily updates (later)

- **Mac/Linux:** add a `cron` entry, e.g. `30 17 * * 1-5` (5:30pm weekdays).
- **Windows:** use Task Scheduler to run the script daily.
- **At scale:** Apache Airflow or Prefect (mention this in your write-up).

## Roadmap

- [x] Week 1: prices + profiles → SQLite
- [ ] Week 2: financial statements + computed ratios
- [ ] Week 4: news ingestion + scheduling
- [ ] Week 5–6: Streamlit app (search → company page → price chart)
- [ ] Later: sentiment, risk scoring, comparison, forecasting
- [ ] Before deploy: migrate SQLite → PostgreSQL

## Data ethics

This project sources data via official APIs/libraries, respects rate limits and
`robots.txt`, identifies itself with a real User-Agent when scraping, and stores
only metadata and derived values (not full copyrighted article text).
