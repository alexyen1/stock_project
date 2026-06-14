"""
Market Lens — Streamlit web app.

Ticker search → company page with an interactive Plotly price chart, reading
straight from the local SQLite database built by the pipeline.

Run from the project root (with the venv active):
    streamlit run app.py
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
from pipeline.queries import get_company, get_prices, list_companies

st.set_page_config(page_title="Market Lens", page_icon="📈", layout="wide")


# --- Cached data access ----------------------------------------------------
# Cache so flipping between tickers / chart options doesn't re-hit the DB.
@st.cache_data(ttl=600)
def load_companies() -> pd.DataFrame:
    return list_companies()


@st.cache_data(ttl=600)
def load_company(ticker: str) -> dict | None:
    return get_company(ticker)


@st.cache_data(ttl=600)
def load_prices(ticker: str) -> pd.DataFrame:
    return get_prices(ticker)


# --- Small helpers ---------------------------------------------------------
def human_market_cap(value) -> str:
    """1_234_000_000 -> '$1.23B'."""
    if value is None:
        return "—"
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(value) >= scale:
            return f"${value / scale:.2f}{unit}"
    return f"${value:,.0f}"


def filter_period(df: pd.DataFrame, label: str) -> pd.DataFrame:
    """Trim the price frame to the selected lookback window."""
    if label == "All" or df.empty:
        return df
    days = {"1M": 30, "3M": 90, "6M": 180, "YTD": None, "1Y": 365}[label]
    if label == "YTD":
        start = pd.Timestamp(df["date"].max().year, 1, 1)
    else:
        start = df["date"].max() - pd.Timedelta(days=days)
    return df[df["date"] >= start]


def price_chart(df: pd.DataFrame, ticker: str, kind: str) -> go.Figure:
    """Price (line or candlestick) on top, volume bars below — shared x-axis."""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.78, 0.22], vertical_spacing=0.03,
    )

    if kind == "Candlestick":
        fig.add_trace(
            go.Candlestick(
                x=df["date"], open=df["open"], high=df["high"],
                low=df["low"], close=df["close"], name=ticker,
            ),
            row=1, col=1,
        )
    else:  # Line (close)
        fig.add_trace(
            go.Scatter(
                x=df["date"], y=df["close"], mode="lines",
                name=ticker, line=dict(width=2),
            ),
            row=1, col=1,
        )

    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], name="Volume",
               marker=dict(color="rgba(120,120,160,0.5)")),
        row=2, col=1,
    )

    fig.update_layout(
        height=560, margin=dict(l=0, r=0, t=10, b=0),
        showlegend=False, xaxis_rangeslider_visible=False,
        hovermode="x unified",
    )
    fig.update_yaxes(title_text="Price ($)", row=1, col=1)
    fig.update_yaxes(title_text="Vol", row=2, col=1)
    return fig


# --- Sidebar: search -------------------------------------------------------
companies = load_companies()

st.sidebar.title("📈 Market Lens")
st.sidebar.caption("Educational use only. Not financial advice.")

query = st.sidebar.text_input("Search ticker or company", placeholder="e.g. AAPL or Apple")
if query:
    mask = (
        companies["ticker"].str.contains(query, case=False, na=False)
        | companies["name"].str.contains(query, case=False, na=False)
    )
    matches = companies[mask]
else:
    matches = companies

if matches.empty:
    st.sidebar.warning("No companies match that search.")
    st.title("Market Lens")
    st.info("No matching companies. Try a different search.")
    st.stop()

labels = [f"{r.ticker} — {r.name}" for r in matches.itertuples()]
choice = st.sidebar.radio("Results", labels, label_visibility="collapsed")
ticker = choice.split(" — ", 1)[0]


# --- Company page ----------------------------------------------------------
company = load_company(ticker)
prices = load_prices(ticker)

st.title(f"{company['name']} ({company['ticker']})")
meta = " · ".join(
    p for p in (company.get("sector"), company.get("industry"), company.get("exchange")) if p
)
if meta:
    st.caption(meta)

# Key metrics from the latest available close.
if not prices.empty:
    latest = prices.iloc[-1]
    prev = prices.iloc[-2] if len(prices) > 1 else latest
    change = latest["close"] - prev["close"]
    pct = (change / prev["close"] * 100) if prev["close"] else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest close", f"${latest['close']:,.2f}",
              f"{change:+.2f} ({pct:+.2f}%)")
    c2.metric("Market cap", human_market_cap(company.get("market_cap")))
    c3.metric("52-wk high", f"${prices['high'].max():,.2f}")
    c4.metric("52-wk low", f"${prices['low'].min():,.2f}")
    st.caption(f"As of {latest['date'].date()} · {len(prices):,} trading days on file")
else:
    st.warning("No price data on file for this ticker yet. Run the ingestion pipeline.")

# Chart controls + chart.
if not prices.empty:
    left, right = st.columns([3, 1])
    with right:
        kind = st.selectbox("Chart type", ["Line (close)", "Candlestick"])
        period = st.radio("Range", ["1M", "3M", "6M", "YTD", "1Y", "All"],
                          index=4, horizontal=True)
    view = filter_period(prices, period)
    st.plotly_chart(
        price_chart(view, ticker, "Candlestick" if kind == "Candlestick" else "Line"),
        width="stretch",
    )

# Company description.
if company.get("description"):
    with st.expander("About the company"):
        st.write(company["description"])
        if company.get("website"):
            st.markdown(f"[Website]({company['website']})")

# Raw data for the curious.
with st.expander("Recent price data"):
    st.dataframe(
        prices.sort_values("date", ascending=False).head(30),
        width="stretch", hide_index=True,
    )

st.sidebar.caption(f"Tracking {len(companies)} companies · DB: {config.DB_PATH.name}")
