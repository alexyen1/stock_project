"""
Market Lens — Week 1 ingestion job.

Fetches daily prices and basic company profiles from yfinance and loads them
into the database (Postgres when DATABASE_URL is set, SQLite otherwise).
The job is IDEMPOTENT: re-running it never creates duplicate rows.

Run from the project root:
    python -m pipeline.ingest_prices
"""
import logging
import time
from datetime import datetime, timezone

import yfinance as yf

import config
from pipeline.db import adapt_sql, db_cursor, init_db, is_postgres

# --- Logging ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_prices")

JOB_NAME = "ingest_prices"
SOURCE = "yfinance"


# --- Company profile -------------------------------------------------------
def upsert_company(cur, ticker: str) -> int | None:
    """Insert or update a company's profile. Returns its company_id."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        log.warning("  profile fetch failed for %s: %s", ticker, exc)
        info = {}

    name = info.get("longName") or info.get("shortName") or ticker
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cur.execute(
        adapt_sql("""
        INSERT INTO companies
            (ticker, name, sector, industry, exchange, country,
             description, market_cap, website, quote_type, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            name        = excluded.name,
            sector      = excluded.sector,
            industry    = excluded.industry,
            exchange    = excluded.exchange,
            country     = excluded.country,
            description = excluded.description,
            market_cap  = excluded.market_cap,
            website     = excluded.website,
            quote_type  = excluded.quote_type,
            updated_at  = excluded.updated_at
        """),
        (
            ticker,
            name,
            info.get("sector"),
            info.get("industry"),
            info.get("exchange"),
            info.get("country"),
            info.get("longBusinessSummary"),
            info.get("marketCap"),
            info.get("website"),
            info.get("quoteType"),
            now,
        ),
    )
    cur.execute(adapt_sql("SELECT company_id FROM companies WHERE ticker = ?"), (ticker,))
    row = cur.fetchone()
    return row["company_id"] if row else None


# --- Prices ----------------------------------------------------------------
def _valid_row(o, h, l, c, v) -> bool:
    """Basic sanity checks before a price row touches the database."""
    vals = [o, h, l, c]
    if any(x is None for x in vals):
        return False
    if any((x != x) for x in vals):               # NaN check (NaN != NaN)
        return False
    if any(x <= 0 for x in vals):                 # prices must be positive
        return False
    if v is not None and v < 0:                   # volume can't be negative
        return False
    return True


def ingest_prices_for(cur, company_id: int, ticker: str) -> tuple[int, int]:
    """Load price history for one ticker. Returns (added, skipped)."""
    df = yf.Ticker(ticker).history(period=config.PRICE_PERIOD, auto_adjust=False)
    if df is None or df.empty:
        log.warning("  no price data returned for %s", ticker)
        return 0, 0

    # Build a dialect-correct INSERT that silently skips duplicate days.
    if is_postgres():
        insert_sql = """
            INSERT INTO stock_prices
                (company_id, date, open, high, low, close, adj_close, volume)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id, date) DO NOTHING
        """
    else:
        insert_sql = """
            INSERT OR IGNORE INTO stock_prices
                (company_id, date, open, high, low, close, adj_close, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """

    added = skipped = 0
    for idx, r in df.iterrows():
        date_str = idx.strftime("%Y-%m-%d")
        o, h, l = r.get("Open"), r.get("High"), r.get("Low")
        c = r.get("Close")
        adj = r.get("Adj Close", c)
        v = r.get("Volume")

        if not _valid_row(o, h, l, c, v):
            skipped += 1
            continue

        cur.execute(
            insert_sql,
            (
                company_id, date_str,
                float(o), float(h), float(l), float(c),
                float(adj) if adj == adj else float(c),
                int(v) if v == v and v is not None else None,
            ),
        )
        if cur.rowcount:        # 1 if inserted, 0 if conflict was skipped
            added += 1
        else:
            skipped += 1
    return added, skipped


# --- Logging the run -------------------------------------------------------
def write_log(cur, started, status, added, skipped, error=None):
    cur.execute(
        adapt_sql("""
        INSERT INTO update_logs
            (job_name, source, run_started_at, run_finished_at,
             status, rows_added, rows_skipped, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """),
        (JOB_NAME, SOURCE, started, datetime.now().isoformat(timespec="seconds"),
         status, added, skipped, error),
    )


# --- Single-ticker ingestion (called from the web UI) ----------------------
def ingest_ticker(ticker: str) -> dict:
    """Ingest one ticker on demand — profile + 1y of prices.

    Returns {"success": True, "name": ..., "prices_added": N}
         or {"success": False, "error": "..."}.
    """
    ticker = ticker.upper().strip()
    try:
        init_db()
        # Quick validation: yfinance sets quoteType for any real symbol.
        info = yf.Ticker(ticker).info or {}
        if not info.get("quoteType"):
            return {
                "success": False,
                "error": f"'{ticker}' not recognised. Check the symbol and try again.",
            }
        with db_cursor() as cur:
            company_id = upsert_company(cur, ticker)
            if company_id is None:
                return {"success": False, "error": f"Could not resolve company for '{ticker}'"}
            added, _ = ingest_prices_for(cur, company_id, ticker)

        # Pull financials immediately so the Fundamentals tab is populated on add.
        # Run in a separate try-except: a financials failure shouldn't undo the add.
        financials_ok = False
        try:
            from pipeline.ingest_financials import upsert_ratios, upsert_statements
            with db_cursor() as cur:
                upsert_statements(cur, company_id, ticker)
                # Reuse the already-fetched info dict — avoids a second yfinance call
                # that commonly fails due to rate limiting on rapid successive requests.
                upsert_ratios(cur, company_id, ticker, info=info)
            financials_ok = True
        except Exception as fin_exc:
            log.warning("  %s: financials ingestion failed: %s", ticker, fin_exc)

        name = info.get("longName") or info.get("shortName") or ticker
        return {
            "success": True,
            "ticker": ticker,
            "name": name,
            "prices_added": added,
            "financials_ok": financials_ok,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# --- Single-ticker removal (called from the web UI) ------------------------
def remove_ticker(ticker: str) -> dict:
    """Delete a ticker and all its data from the database.

    Returns {"success": True, "name": ...}
         or {"success": False, "error": "..."}.
    """
    ticker = ticker.upper().strip()
    try:
        with db_cursor() as cur:
            cur.execute(adapt_sql("SELECT company_id, name FROM companies WHERE ticker = ?"), (ticker,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"'{ticker}' is not in the database."}
            company_id = row["company_id"]
            name       = row["name"]

            # Delete child rows in FK-safe order before removing the company.
            for table in ("sentiment_scores", "watchlists", "financial_ratios",
                          "financial_statements", "stock_prices", "news_articles"):
                cur.execute(adapt_sql(f"DELETE FROM {table} WHERE company_id = ?"), (company_id,))
            cur.execute(adapt_sql("DELETE FROM companies WHERE company_id = ?"), (company_id,))

        return {"success": True, "ticker": ticker, "name": name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


# --- Orchestration ---------------------------------------------------------
def run():
    started = datetime.now().isoformat(timespec="seconds")
    db_type = "Postgres" if is_postgres() else f"SQLite ({config.DB_PATH})"
    log.info("Initializing database (%s)...", db_type)
    init_db()

    # Merge config list with any tickers added dynamically via the web app.
    try:
        with db_cursor() as cur:
            cur.execute("SELECT ticker FROM companies ORDER BY ticker")
            db_tickers = [row["ticker"] for row in cur.fetchall()]
    except Exception:
        db_tickers = []
    tickers = list(dict.fromkeys(config.TICKERS + db_tickers))

    total_added = total_skipped = 0
    failures = []

    for ticker in tickers:
        log.info("Processing %s ...", ticker)
        try:
            with db_cursor() as cur:
                company_id = upsert_company(cur, ticker)
                if company_id is None:
                    raise RuntimeError("could not resolve company_id")
                added, skipped = ingest_prices_for(cur, company_id, ticker)
            total_added += added
            total_skipped += skipped
            log.info("  %s: +%d new, %d skipped", ticker, added, skipped)
        except Exception as exc:
            failures.append(ticker)
            log.error("  %s FAILED: %s", ticker, exc)
        time.sleep(0.5)                            # be polite; avoid rate limits

    status = "success" if not failures else (
        "failed" if len(failures) == len(tickers) else "partial"
    )
    err = None if not failures else f"failed tickers: {', '.join(failures)}"

    with db_cursor() as cur:
        write_log(cur, started, status, total_added, total_skipped, err)

    log.info("-" * 52)
    log.info("Done. status=%s  added=%d  skipped=%d  failed=%d",
             status, total_added, total_skipped, len(failures))
    log.info("Database: %s", db_type)


if __name__ == "__main__":
    run()
