"""Read-only queries for the web app.

These are pure data-access helpers — no caching, no Streamlit imports — so they
stay reusable and easy to test. The app layer wraps them with st.cache_data.
"""
from contextlib import closing

import pandas as pd

from pipeline.db import get_connection


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
        row = conn.execute(
            "SELECT * FROM companies WHERE ticker = ?", (ticker,)
        ).fetchone()
    return dict(row) if row else None


def get_prices(ticker: str) -> pd.DataFrame:
    """Daily OHLCV for one ticker as a DataFrame (ascending by date).

    Empty DataFrame if the ticker is unknown or has no price rows.
    """
    with closing(get_connection()) as conn:
        df = pd.read_sql_query(
            """
            SELECT p.date, p.open, p.high, p.low, p.close, p.adj_close, p.volume
            FROM stock_prices p
            JOIN companies c ON c.company_id = p.company_id
            WHERE c.ticker = ?
            ORDER BY p.date
            """,
            conn,
            params=(ticker,),
            parse_dates=["date"],
        )
    return df
