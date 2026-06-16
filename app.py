"""
Market Lens — Streamlit web app.

Ticker search → company page with two tabs:
  • Price    — interactive Plotly OHLCV chart
  • Fundamentals — quarterly financials + TTM ratios

Run from the project root (with the venv active):
    streamlit run app.py
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import config
from pipeline.queries import (
    get_company, get_financials, get_prices, get_ratios, list_companies,
)

st.set_page_config(page_title="Market Lens", page_icon="📈", layout="wide")


# --- Cached data access ----------------------------------------------------
@st.cache_data(ttl=600)
def load_companies() -> pd.DataFrame:
    return list_companies()

@st.cache_data(ttl=600)
def load_company(ticker: str) -> dict | None:
    return get_company(ticker)

@st.cache_data(ttl=600)
def load_prices(ticker: str) -> pd.DataFrame:
    return get_prices(ticker)

@st.cache_data(ttl=600)
def load_financials(ticker: str) -> pd.DataFrame:
    return get_financials(ticker)

@st.cache_data(ttl=600)
def load_ratios(ticker: str) -> dict | None:
    return get_ratios(ticker)


# --- Formatting helpers ----------------------------------------------------
def fmt_currency(value, suffix="") -> str:
    if value is None:
        return "—"
    for unit, scale in (("T", 1e12), ("B", 1e9), ("M", 1e6)):
        if abs(value) >= scale:
            return f"${value / scale:.2f}{unit}{suffix}"
    return f"${value:,.0f}{suffix}"

def fmt_pct(value) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"

def fmt_ratio(value, suffix="×") -> str:
    if value is None:
        return "—"
    return f"{value:.2f}{suffix}"

def human_market_cap(value) -> str:
    return fmt_currency(value)

def filter_period(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if label == "All" or df.empty:
        return df
    days = {"1M": 30, "3M": 90, "6M": 180, "YTD": None, "1Y": 365}[label]
    if label == "YTD":
        start = pd.Timestamp(df["date"].max().year, 1, 1)
    else:
        start = df["date"].max() - pd.Timedelta(days=days)
    return df[df["date"] >= start]


# --- Chart builders --------------------------------------------------------
def price_chart(df: pd.DataFrame, ticker: str, kind: str) -> go.Figure:
    """Price (line or candlestick) on top, volume bars below."""
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
    else:
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


def financials_chart(df: pd.DataFrame) -> go.Figure:
    """Grouped bar chart: Revenue vs Net Income by quarter."""
    quarters = df["period"].tolist()[::-1]     # chronological order
    revenue    = (df["revenue"].tolist()[::-1])
    net_income = (df["net_income"].tolist()[::-1])

    fig = go.Figure(data=[
        go.Bar(name="Revenue",    x=quarters, y=revenue,
               marker_color="steelblue"),
        go.Bar(name="Net Income", x=quarters, y=net_income,
               marker_color="mediumseagreen"),
    ])
    fig.update_layout(
        barmode="group", height=340,
        margin=dict(l=0, r=0, t=10, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        yaxis_tickprefix="$", yaxis_tickformat=".2s",
        hovermode="x unified",
    )
    return fig


# --- Sidebar: search -------------------------------------------------------
companies = load_companies()

st.sidebar.title("Market Analysis")

query = st.sidebar.text_input(
    "Search ticker or company", placeholder="e.g. AAPL or Apple"
)
matches = companies[
    companies["ticker"].str.contains(query, case=False, na=False)
    | companies["name"].str.contains(query, case=False, na=False)
] if query else companies

if matches.empty:
    st.sidebar.warning("No companies match that search.")
    st.title("Market Lens")
    st.info("No matching companies. Try a different search.")
    st.stop()

labels = [f"{r.ticker} — {r.name}" for r in matches.itertuples()]
choice = st.sidebar.radio("Results", labels, label_visibility="collapsed")
ticker = choice.split(" — ", 1)[0]


# --- Company header (always visible) ---------------------------------------
company  = load_company(ticker)
prices   = load_prices(ticker)
fin_df   = load_financials(ticker)
ratios   = load_ratios(ticker)

st.title(f"{company['name']} ({company['ticker']})")
meta = " · ".join(
    p for p in (company.get("sector"), company.get("industry"), company.get("exchange")) if p
)
if meta:
    st.caption(meta)

# Key price metrics strip — shown above both tabs.
if not prices.empty:
    latest = prices.iloc[-1]
    prev   = prices.iloc[-2] if len(prices) > 1 else latest
    change = latest["close"] - prev["close"]
    pct    = (change / prev["close"] * 100) if prev["close"] else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Latest close", f"${latest['close']:,.2f}",
              f"{change:+.2f} ({pct:+.2f}%)")
    c2.metric("Market cap", human_market_cap(company.get("market_cap")))
    c3.metric("52-wk high", f"${prices['high'].max():,.2f}")
    c4.metric("52-wk low",  f"${prices['low'].min():,.2f}")
    st.caption(
        f"As of {latest['date'].date()} · {len(prices):,} trading days on file"
    )
else:
    st.warning("No price data on file for this ticker yet. Run the ingestion pipeline.")


# --- Tabs ------------------------------------------------------------------
tab_price, tab_fundamentals = st.tabs(["📈 Price", "📊 Fundamentals"])


# ── Price tab ──────────────────────────────────────────────────────────────
with tab_price:
    if not prices.empty:
        left, right = st.columns([3, 1])
        with right:
            kind   = st.selectbox("Chart type", ["Line (close)", "Candlestick"])
            period = st.radio("Range", ["1M", "3M", "6M", "YTD", "1Y", "All"],
                              index=4, horizontal=True)
        view = filter_period(prices, period)
        st.plotly_chart(
            price_chart(view, ticker, "Candlestick" if kind == "Candlestick" else "Line"),
            width="stretch",
        )

    if company.get("description"):
        with st.expander("About the company"):
            st.write(company["description"])
            if company.get("website"):
                st.markdown(f"[Website]({company['website']})")

    with st.expander("Recent price data"):
        st.dataframe(
            prices.sort_values("date", ascending=False).head(30),
            width="stretch", hide_index=True,
        )


# ── Fundamentals tab ───────────────────────────────────────────────────────
with tab_fundamentals:
    if ratios is None and fin_df.empty:
        st.info(
            "No financial data yet. Run the ingestion job first:\n\n"
            "```\npython -m pipeline.ingest_financials\n```"
        )
    else:
        # --- TTM ratio grid ------------------------------------------------
        if ratios:
            st.subheader("Key ratios (trailing twelve months)")
            r1, r2, r3, r4, r5, r6 = st.columns(6)
            r1.metric("P/E ratio",      fmt_ratio(ratios.get("pe_ratio")))
            r2.metric("Profit margin",  fmt_pct(ratios.get("profit_margin")))
            r3.metric("ROE",            fmt_pct(ratios.get("roe")))
            r4.metric("ROA",            fmt_pct(ratios.get("roa")))
            # yfinance returns debt_to_equity as a percentage (173 = 1.73×)
            de = ratios.get("debt_to_equity")
            r5.metric("Debt / Equity",  fmt_ratio((de / 100) if de else None))
            r6.metric("Current ratio",  fmt_ratio(ratios.get("current_ratio"), suffix=""))
            st.divider()

        # --- Revenue & Net Income chart ------------------------------------
        if not fin_df.empty:
            st.subheader("Quarterly revenue & net income")
            chart_df = fin_df.dropna(subset=["revenue", "net_income"])
            if not chart_df.empty:
                st.plotly_chart(financials_chart(chart_df), width="stretch")

            # --- EPS & cash flow metrics -----------------------------------
            st.subheader("Per-quarter snapshot")
            e1, e2, e3 = st.columns(3)
            latest_q = fin_df.iloc[0]
            e1.metric("EPS (latest quarter)",
                      f"${latest_q['eps']:.2f}" if pd.notna(latest_q.get("eps")) else "—")
            e2.metric("Operating cash flow",
                      fmt_currency(latest_q.get("operating_cash_flow")))
            e3.metric("Total equity",
                      fmt_currency(latest_q.get("total_equity")))
            st.divider()

            # --- Quarterly table -------------------------------------------
            with st.expander("Full quarterly breakdown"):
                display = fin_df.copy()
                for col in ["revenue", "gross_profit", "operating_income",
                            "net_income", "total_assets", "total_liabilities",
                            "total_equity", "operating_cash_flow"]:
                    if col in display.columns:
                        display[col] = display[col].apply(
                            lambda v: fmt_currency(v) if pd.notna(v) else "—"
                        )
                if "eps" in display.columns:
                    display["eps"] = display["eps"].apply(
                        lambda v: f"${v:.2f}" if pd.notna(v) else "—"
                    )
                st.dataframe(display, width="stretch", hide_index=True)

st.sidebar.caption(
    f"Tracking {len(companies)} companies · DB: {config.DB_PATH.name}"
)
