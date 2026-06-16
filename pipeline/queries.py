"""Read-only queries for the web app.

Pure data-access helpers — no caching, no Streamlit imports — so they stay
reusable and easy to test. The app layer wraps them with st.cache_data.
"""
from contextlib import closing

import pandas as pd

from pipeline.db import adapt_sql, get_connection, is_postgres


def list_companies() -> pd.DataFrame:
    """All tracked companies, ordered by ticker. Columns: ticker, name, sector."""
    with closing(get_connection()) as conn:
        return pd.read_sql_query(
            "SELECT ticker, name, sector FROM companies ORDER BY ticker",
            conn,
        )


def get_company(ticker: str) -> dict | None:
    """Full profile for one ticker, or None if it isn't tracked."""
    with closing(get_connection()) as conn:
        if is_postgres():
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(adapt_sql("SELECT * FROM companies WHERE ticker = ?"), (ticker,))
        row = cur.fetchone()
    return dict(row) if row else None


def get_financials(ticker: str) -> pd.DataFrame:
    """Quarterly combined financial statements, newest first (up to 4 rows)."""
    with closing(get_connection()) as conn:
        return pd.read_sql_query(
            adapt_sql("""
            SELECT fs.period, fs.period_end_date,
                   fs.revenue, fs.gross_profit, fs.operating_income,
                   fs.net_income, fs.eps,
                   fs.total_assets, fs.total_liabilities, fs.total_equity,
                   fs.operating_cash_flow
            FROM financial_statements fs
            JOIN companies c ON c.company_id = fs.company_id
            WHERE c.ticker = ? AND fs.statement_type = 'combined'
            ORDER BY fs.period_end_date DESC
            LIMIT 4
            """),
            conn,
            params=(ticker,),
        )


def get_ratios(ticker: str) -> dict | None:
    """Latest TTM financial ratios for one ticker, or None if not yet ingested."""
    with closing(get_connection()) as conn:
        if is_postgres():
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        cur.execute(
            adapt_sql("""
            SELECT fr.pe_ratio, fr.profit_margin, fr.current_ratio,
                   fr.debt_to_equity, fr.roe, fr.roa, fr.quick_ratio
            FROM financial_ratios fr
            JOIN companies c ON c.company_id = fr.company_id
            WHERE c.ticker = ? AND fr.period = 'TTM'
            """),
            (ticker,),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def get_prices(ticker: str) -> pd.DataFrame:
    """Daily OHLCV for one ticker as a DataFrame (ascending by date).

    Empty DataFrame if the ticker is unknown or has no price rows.
    """
    with closing(get_connection()) as conn:
        df = pd.read_sql_query(
            adapt_sql("""
            SELECT p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume
            FROM stock_prices p
            JOIN companies c ON c.company_id = p.company_id
            WHERE c.ticker = ?
            ORDER BY p.date
            """),
            conn,
            params=(ticker,),
            parse_dates=["date"],
        )
    return df
