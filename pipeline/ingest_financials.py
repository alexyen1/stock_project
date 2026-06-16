"""
Market Lens — Financial statements + ratios ingestion job.

Pulls the last 4 quarters of income statement, balance sheet, and cash flow
data from yfinance, plus trailing-twelve-month ratios, and upserts them into
the database. Safe to re-run — all inserts use ON CONFLICT DO UPDATE.

Run from the project root:
    python -m pipeline.ingest_financials
"""
import logging
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import config
from pipeline.db import adapt_sql, db_cursor, init_db, is_postgres

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_financials")

JOB_NAME = "ingest_financials"
SOURCE = "yfinance"


# --- Helpers ---------------------------------------------------------------

def _quarter_label(dt) -> str:
    """Convert a date to 'YYYY-QN' string, e.g. 2025-03-31 → '2025-Q1'."""
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _get(df, col, *row_keys):
    """Safely extract the first matching row value from a DataFrame column."""
    if df is None or df.empty or col not in df.columns:
        return None
    for key in row_keys:
        if key in df.index:
            val = df.loc[key, col]
            if pd.notna(val):
                return float(val)
    return None


def _get_company_id(cur, ticker: str) -> int | None:
    cur.execute(adapt_sql("SELECT company_id FROM companies WHERE ticker = ?"), (ticker,))
    row = cur.fetchone()
    return row["company_id"] if row else None


# --- Statements ------------------------------------------------------------

def upsert_statements(cur, company_id: int, ticker: str) -> int:
    """Upsert the last 4 quarters of combined financials. Returns rows written."""
    t = yf.Ticker(ticker)

    try:
        inc = t.quarterly_income_stmt
    except Exception:
        inc = None
    try:
        bal = t.quarterly_balance_sheet
    except Exception:
        bal = None
    try:
        cf = t.quarterly_cashflow
    except Exception:
        cf = None

    source_df = inc if (inc is not None and not inc.empty) else bal
    if source_df is None or source_df.empty:
        log.warning("  %s: no quarterly statement data available", ticker)
        return 0

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    written = 0

    for col in source_df.columns[:4]:       # most-recent 4 quarters
        period      = _quarter_label(col)
        period_end  = col.strftime("%Y-%m-%d")

        revenue          = _get(inc, col, "Total Revenue")
        gross_profit     = _get(inc, col, "Gross Profit")
        operating_income = _get(inc, col, "Operating Income", "EBIT")
        net_income       = _get(inc, col, "Net Income")
        eps              = _get(inc, col, "Basic EPS", "Diluted EPS",
                                "Basic Earnings Per Share", "Diluted Earnings Per Share")
        total_assets     = _get(bal, col, "Total Assets")
        total_liab       = _get(bal, col, "Total Liabilities Net Minority Interest",
                                "Total Liabilities")
        total_equity     = _get(bal, col, "Stockholders Equity",
                                "Total Equity Gross Minority Interest")
        op_cash_flow     = _get(cf,  col, "Operating Cash Flow")

        cur.execute(
            adapt_sql("""
            INSERT INTO financial_statements
                (company_id, period, period_end_date, statement_type,
                 revenue, net_income, gross_profit, operating_income,
                 total_assets, total_liabilities, total_equity,
                 eps, operating_cash_flow, source)
            VALUES (?, ?, ?, 'combined', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (company_id, period, statement_type) DO UPDATE SET
                period_end_date     = excluded.period_end_date,
                revenue             = excluded.revenue,
                net_income          = excluded.net_income,
                gross_profit        = excluded.gross_profit,
                operating_income    = excluded.operating_income,
                total_assets        = excluded.total_assets,
                total_liabilities   = excluded.total_liabilities,
                total_equity        = excluded.total_equity,
                eps                 = excluded.eps,
                operating_cash_flow = excluded.operating_cash_flow,
                source              = excluded.source
            """),
            (company_id, period, period_end,
             revenue, net_income, gross_profit, operating_income,
             total_assets, total_liab, total_equity,
             eps, op_cash_flow, SOURCE),
        )
        written += 1

    return written


# --- Ratios ----------------------------------------------------------------

def upsert_ratios(cur, company_id: int, ticker: str) -> bool:
    """Upsert trailing-twelve-month ratios from yfinance .info. Returns True on success."""
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as exc:
        log.warning("  %s: could not fetch info for ratios: %s", ticker, exc)
        return False

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    cur.execute(
        adapt_sql("""
        INSERT INTO financial_ratios
            (company_id, period, pe_ratio, profit_margin,
             current_ratio, debt_to_equity, roe, roa, quick_ratio, computed_at)
        VALUES (?, 'TTM', ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (company_id, period) DO UPDATE SET
            pe_ratio       = excluded.pe_ratio,
            profit_margin  = excluded.profit_margin,
            current_ratio  = excluded.current_ratio,
            debt_to_equity = excluded.debt_to_equity,
            roe            = excluded.roe,
            roa            = excluded.roa,
            quick_ratio    = excluded.quick_ratio,
            computed_at    = excluded.computed_at
        """),
        (
            company_id,
            info.get("trailingPE"),
            info.get("profitMargins"),
            info.get("currentRatio"),
            info.get("debtToEquity"),
            info.get("returnOnEquity"),
            info.get("returnOnAssets"),
            info.get("quickRatio"),
            now,
        ),
    )
    return True


# --- Run log ---------------------------------------------------------------

def write_log(cur, started, status, rows_added, error=None):
    cur.execute(
        adapt_sql("""
        INSERT INTO update_logs
            (job_name, source, run_started_at, run_finished_at,
             status, rows_added, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """),
        (JOB_NAME, SOURCE, started,
         datetime.now().isoformat(timespec="seconds"),
         status, rows_added, error),
    )


# --- Orchestration ---------------------------------------------------------

def run():
    started = datetime.now().isoformat(timespec="seconds")
    db_type = "Postgres" if is_postgres() else f"SQLite ({config.DB_PATH})"
    log.info("Ingesting financials → %s", db_type)
    init_db()

    total_rows = 0
    failures = []

    for ticker in config.TICKERS:
        log.info("Processing %s ...", ticker)
        try:
            with db_cursor() as cur:
                company_id = _get_company_id(cur, ticker)
                if company_id is None:
                    raise RuntimeError(f"{ticker} not found in companies table — run ingest_prices first")
                rows = upsert_statements(cur, company_id, ticker)
                upsert_ratios(cur, company_id, ticker)
            total_rows += rows
            log.info("  %s: %d statement rows upserted", ticker, rows)
        except Exception as exc:
            failures.append(ticker)
            log.error("  %s FAILED: %s", ticker, exc)
        time.sleep(0.5)

    status = "success" if not failures else (
        "failed" if len(failures) == len(config.TICKERS) else "partial"
    )
    err = None if not failures else f"failed tickers: {', '.join(failures)}"

    with db_cursor() as cur:
        write_log(cur, started, status, total_rows, err)

    log.info("-" * 52)
    log.info("Done. status=%s  rows=%d  failed=%d", status, total_rows, len(failures))


if __name__ == "__main__":
    run()
