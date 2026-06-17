-- Market Lens database schema — PostgreSQL version.
-- Run once in the Supabase SQL Editor to create all tables.
-- All statements use IF NOT EXISTS so this file is safe to re-run.

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id   SERIAL PRIMARY KEY,
    ticker       TEXT NOT NULL UNIQUE,
    name         TEXT,
    sector       TEXT,
    industry     TEXT,
    exchange     TEXT,
    country      TEXT,
    description  TEXT,
    market_cap   BIGINT,
    website      TEXT,
    quote_type   TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- stock_prices
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices (
    price_id    SERIAL PRIMARY KEY,
    company_id  INTEGER NOT NULL REFERENCES companies (company_id),
    date        DATE NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    adj_close   DOUBLE PRECISION,
    volume      BIGINT,
    UNIQUE (company_id, date)
);
CREATE INDEX IF NOT EXISTS idx_prices_company_date ON stock_prices (company_id, date);

-- ---------------------------------------------------------------------------
-- financial_statements
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_statements (
    statement_id        SERIAL PRIMARY KEY,
    company_id          INTEGER NOT NULL REFERENCES companies (company_id),
    period              TEXT NOT NULL,
    period_end_date     DATE,
    statement_type      TEXT NOT NULL,
    revenue             DOUBLE PRECISION,
    net_income          DOUBLE PRECISION,
    gross_profit        DOUBLE PRECISION,
    operating_income    DOUBLE PRECISION,
    total_assets        DOUBLE PRECISION,
    total_liabilities   DOUBLE PRECISION,
    total_equity        DOUBLE PRECISION,
    eps                 DOUBLE PRECISION,
    operating_cash_flow DOUBLE PRECISION,
    currency            TEXT,
    source              TEXT,
    UNIQUE (company_id, period, statement_type)
);

-- ---------------------------------------------------------------------------
-- financial_ratios
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_ratios (
    ratio_id        SERIAL PRIMARY KEY,
    company_id      INTEGER NOT NULL REFERENCES companies (company_id),
    period          TEXT,
    pe_ratio        DOUBLE PRECISION,
    profit_margin   DOUBLE PRECISION,
    current_ratio   DOUBLE PRECISION,
    debt_to_equity  DOUBLE PRECISION,
    roe             DOUBLE PRECISION,
    roa             DOUBLE PRECISION,
    quick_ratio     DOUBLE PRECISION,
    computed_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (company_id, period)
);

-- ---------------------------------------------------------------------------
-- news_articles
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_articles (
    article_id   SERIAL PRIMARY KEY,
    company_id   INTEGER REFERENCES companies (company_id),
    headline     TEXT,
    summary      TEXT,
    source       TEXT,
    url          TEXT NOT NULL UNIQUE,
    published_at TIMESTAMPTZ,
    fetched_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles (published_at);

-- ---------------------------------------------------------------------------
-- sentiment_scores
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sentiment_scores (
    sentiment_id    SERIAL PRIMARY KEY,
    article_id      INTEGER REFERENCES news_articles (article_id),
    company_id      INTEGER REFERENCES companies (company_id),
    source_type     TEXT,
    date            DATE,
    sentiment_score DOUBLE PRECISION,
    sentiment_label TEXT,
    model_used      TEXT
);

-- ---------------------------------------------------------------------------
-- users + watchlists
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       SERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id SERIAL PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users (user_id),
    company_id   INTEGER NOT NULL REFERENCES companies (company_id),
    added_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, company_id)
);

-- ---------------------------------------------------------------------------
-- update_logs
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS update_logs (
    log_id          SERIAL PRIMARY KEY,
    job_name        TEXT,
    source          TEXT,
    run_started_at  TIMESTAMPTZ,
    run_finished_at TIMESTAMPTZ,
    status          TEXT,
    rows_added      INTEGER DEFAULT 0,
    rows_skipped    INTEGER DEFAULT 0,
    error_message   TEXT
);
