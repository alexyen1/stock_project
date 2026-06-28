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
from pipeline.alerts import create_alert, delete_alert, list_alerts, triggered_alerts
from pipeline.queries import (
    get_company, get_financials, get_prices, get_ratios, list_companies,
)

st.set_page_config(page_title="Market Lens", page_icon="📈", layout="wide")


@st.cache_resource
def ensure_schema() -> None:
    from pipeline.db import init_db
    init_db()

ensure_schema()


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

@st.cache_data(ttl=600)
def load_etf_info(ticker: str) -> dict:
    """Fetch ETF metadata directly from yfinance (cached 10 min)."""
    import yfinance as yf
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}

@st.cache_data(ttl=900)
def load_news(ticker: str, company_name: str | None) -> list[dict]:
    from pipeline.news import get_news
    return get_news(ticker, company_name)


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
    "🔍 Search ticker or company", label_visibility="collapsed"
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

# --- Add ticker ------------------------------------------------------------
with st.sidebar.expander("➕ Add a ticker"):
    with st.form("add_ticker_form", clear_on_submit=True):
        new_ticker = st.text_input(
            "Ticker symbol",
            label_visibility="collapsed",
            help="Stocks and ETFs both work. Use the exact symbol from Yahoo Finance.",
        )
        submitted = st.form_submit_button("Add", use_container_width=True)
    if submitted and new_ticker.strip():
        from pipeline.ingest_prices import ingest_ticker
        with st.spinner(f"Fetching {new_ticker.upper().strip()}…"):
            result = ingest_ticker(new_ticker)
        if result["success"]:
            msg = (
                f"Added **{result['name']}** ({result['ticker']}) "
                f"— {result['prices_added']} price rows loaded."
            )
            if not result.get("financials_ok"):
                msg += " Financials will appear after the next scheduled run."
            st.sidebar.success(msg)
            st.cache_data.clear()
            st.rerun()
        else:
            st.sidebar.error(result["error"])

# --- Remove ticker ---------------------------------------------------------
with st.sidebar.expander("🗑️ Remove a ticker"):
    ticker_to_remove = st.selectbox(
        "Select ticker", companies["ticker"].tolist(), key="remove_select",
        label_visibility="collapsed",
    )
    if ticker_to_remove in config.TICKERS:
        st.warning(
            "This is a default ticker — it will be re-added on the next scheduled run.",
            icon="⚠️",
        )
    confirmed = st.checkbox("Delete all data for this ticker", key="remove_confirm")
    if st.button("Remove", disabled=not confirmed, type="primary", key="remove_btn"):
        from pipeline.ingest_prices import remove_ticker
        with st.spinner(f"Removing {ticker_to_remove}…"):
            result = remove_ticker(ticker_to_remove)
        if result["success"]:
            st.session_state.pop("remove_error", None)
            st.sidebar.success(f"Removed **{result['name']}** ({result['ticker']}).")
            st.cache_data.clear()
            st.rerun()
        else:
            st.session_state["remove_error"] = result["error"]
    # Show persisted error outside the button block so it survives reruns.
    if "remove_error" in st.session_state:
        st.error(st.session_state["remove_error"])

# --- Price alerts ------------------------------------------------------------
with st.sidebar.expander(f"🔔 Alerts for {ticker}"):
    existing_alerts = list_alerts(ticker)
    if existing_alerts:
        for a in existing_alerts:
            col1, col2 = st.columns([4, 1])
            col1.write(f"{a['direction'].capitalize()} ${a['threshold_price']:,.2f}")
            if col2.button("✕", key=f"del_alert_{a['alert_id']}"):
                delete_alert(a["alert_id"])
                st.rerun()
    else:
        st.caption("No alerts set for this ticker yet.")

    with st.form(f"add_alert_form_{ticker}", clear_on_submit=True):
        d1, d2 = st.columns(2)
        direction = d1.selectbox("Direction", ["above", "below"], label_visibility="collapsed")
        threshold = d2.number_input(
            "Threshold price ($)", min_value=0.0, step=1.0, label_visibility="collapsed",
        )
        alert_submitted = st.form_submit_button("Set alert", use_container_width=True)
    if alert_submitted:
        alert_result = create_alert(ticker, direction, threshold)
        if alert_result["success"]:
            st.rerun()
        else:
            st.error(alert_result["error"])


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

    for hit in triggered_alerts(list_alerts(ticker), latest["close"]):
        cmp_symbol = "≥" if hit["direction"] == "above" else "≤"
        st.warning(
            f"🔔 {ticker} closed at ${latest['close']:,.2f} — {cmp_symbol} your "
            f"${hit['threshold_price']:,.2f} alert threshold.",
            icon="🔔",
        )
else:
    st.warning("No price data on file for this ticker yet. Run the ingestion pipeline.")


# --- Tabs ------------------------------------------------------------------
tab_price, tab_fundamentals, tab_news = st.tabs(["Price", "Fundamentals", "News"])


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
    quote_type = (company.get("quote_type") or "").upper()

    # ── ETF / mutual-fund view ─────────────────────────────────────────────
    if quote_type in ("ETF", "MUTUALFUND"):
        etf = load_etf_info(ticker)

        st.subheader("Fund overview")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Assets (AUM)", fmt_currency(etf.get("totalAssets")),
            help="Total assets under management — the total amount of money invested in this fund.",
        )
        expense = etf.get("annualReportExpenseRatio") or etf.get("expenseRatio")
        c2.metric(
            "Expense ratio", fmt_pct(expense),
            help=(
                "The annual fee charged by the fund, as a percentage of your investment. "
                "Most index ETFs charge 0.03%–0.20%; actively managed funds charge more."
            ),
        )
        div_yield = etf.get("yield") or etf.get("trailingAnnualDividendYield")
        c3.metric(
            "Dividend yield", fmt_pct(div_yield),
            help="Annual distributions (dividends) paid out to investors, as a % of the current price.",
        )
        c4.metric(
            "Category", etf.get("category") or "—",
            help="The fund's investment style, e.g. 'Large Blend', 'Short-Term Bond'.",
        )

        st.subheader("Performance")
        p1, p2, p3 = st.columns(3)
        p1.metric(
            "YTD return", fmt_pct(etf.get("ytdReturn")),
            help="How much the fund has returned since January 1 of the current year.",
        )
        p2.metric(
            "3-year avg return", fmt_pct(etf.get("threeYearAverageReturn")),
            help="Average annual return over the past 3 years.",
        )
        p3.metric(
            "5-year avg return", fmt_pct(etf.get("fiveYearAverageReturn")),
            help="Average annual return over the past 5 years.",
        )

        st.subheader("Risk & valuation")
        v1, v2, v3 = st.columns(3)
        beta = etf.get("beta3Year") or etf.get("beta")
        v1.metric(
            "Beta (3Y)", fmt_ratio(beta, suffix=""),
            help=(
                "How much the fund moves relative to the broader market. "
                "1.0 = moves in line with the market. "
                "Above 1.0 = more volatile; below 1.0 = more stable."
            ),
        )
        v2.metric(
            "P/E (holdings)", fmt_ratio(etf.get("trailingPE")),
            help=(
                "The weighted-average Price-to-Earnings ratio of all stocks inside this fund. "
                "A rough sense of how expensively the fund's holdings are priced relative to their earnings."
            ),
        )
        v3.metric(
            "Number of holdings", str(etf.get("holdings_count") or etf.get("numberOfHoldings") or "—"),
            help="How many individual securities the fund holds.",
        )

        fund_desc = etf.get("longBusinessSummary")
        if fund_desc:
            with st.expander("About this fund"):
                st.write(fund_desc)

    # ── Stock view ─────────────────────────────────────────────────────────
    else:
        if ratios is None and fin_df.empty:
            st.info(
                "No financial data yet. Run the ingestion job first:\n\n"
                "```\npython -m pipeline.ingest_financials\n```"
            )
        else:
            # --- TTM ratio grid --------------------------------------------
            if ratios:
                st.subheader("Key ratios (trailing twelve months)")
                r1, r2, r3, r4, r5, r6 = st.columns(6)
                r1.metric(
                    "P/E ratio", fmt_ratio(ratios.get("pe_ratio")),
                    help=(
                        "Price-to-Earnings — how much investors pay for every $1 the company earns. "
                        "A P/E of 20 means you're paying $20 for $1 of annual profit. "
                        "Lower can mean cheaper; higher often reflects expectations of faster growth."
                    ),
                )
                r2.metric(
                    "Profit margin", fmt_pct(ratios.get("profit_margin")),
                    help=(
                        "How many cents of profit the company keeps from every $1 of revenue. "
                        "A 25% margin means $0.25 profit per $1 sold. Higher is generally better."
                    ),
                )
                r3.metric(
                    "ROE", fmt_pct(ratios.get("roe")),
                    help=(
                        "Return on Equity — how much profit the company generates for every $1 "
                        "shareholders have invested. A 15% ROE means $0.15 of profit per $1 of equity. "
                        "Higher is better, but very high values can also signal heavy debt."
                    ),
                )
                r4.metric(
                    "ROA", fmt_pct(ratios.get("roa")),
                    help=(
                        "Return on Assets — how efficiently the company uses everything it owns "
                        "to generate profit. A 10% ROA means $0.10 of profit per $1 of assets. "
                        "Useful for comparing companies in the same industry."
                    ),
                )
                # yfinance returns debt_to_equity as a percentage (173 = 1.73×)
                de = ratios.get("debt_to_equity")
                r5.metric(
                    "Debt / Equity", fmt_ratio((de / 100) if de else None),
                    help=(
                        "How much debt the company carries relative to what shareholders own. "
                        "A ratio of 1.5× means $1.50 of debt for every $1 of equity. "
                        "Higher means more financial risk, but some industries naturally carry more debt."
                    ),
                )
                r6.metric(
                    "Current ratio", fmt_ratio(ratios.get("current_ratio"), suffix=""),
                    help=(
                        "Whether the company can pay its short-term bills. "
                        "A ratio above 1.0 means it has more short-term assets than short-term debts — "
                        "generally healthy. Below 1.0 can be a warning sign."
                    ),
                )
                st.divider()

            # --- Revenue & Net Income chart --------------------------------
            if not fin_df.empty:
                st.subheader("Quarterly revenue & net income")
                chart_df = fin_df.dropna(subset=["revenue", "net_income"])
                if not chart_df.empty:
                    st.plotly_chart(financials_chart(chart_df), width="stretch")

                # --- EPS & cash flow metrics -------------------------------
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

                # --- Quarterly table ---------------------------------------
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


# ── News tab ────────────────────────────────────────────────────────────────
with tab_news:
    with st.spinner("Loading news…"):
        articles = load_news(ticker, company.get("name"))

    if not articles:
        st.info("No recent news found for this ticker.")
    else:
        for art in articles:
            when = art["published_at"].strftime("%b %d, %Y") if art["published_at"] else ""
            st.markdown(f"**[{art['headline']}]({art['url']})**")
            st.caption(" · ".join(p for p in (art["source"], when) if p))
            if art["summary"]:
                st.write(art["summary"])
            st.divider()

st.sidebar.caption(
    f"Tracking {len(companies)} companies · DB: {config.DB_PATH.name}"
)
