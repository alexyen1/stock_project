-- Market Lens database schema (SQLite-first).
-- Notes for PostgreSQL migration are in comments.
-- All statements use IF NOT EXISTS so this file is safe to re-run.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- companies: one row per public company
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    company_id   INTEGER PRIMARY KEY AUTOINCREMENT,  -- Postgres: SERIAL/IDENTITY
    ticker       TEXT NOT NULL UNIQUE,
    name         TEXT,
    sector       TEXT,
    industry     TEXT,
    exchange     TEXT,
    country      TEXT,
    description  TEXT,
    market_cap   INTEGER,
    website      TEXT,
    quote_type   TEXT,
    created_at   TEXT DEFAULT (datetime('now')),     -- Postgres: TIMESTAMPTZ DEFAULT now()
    updated_at   TEXT DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- stock_prices: daily OHLCV. One row per company per day.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS stock_prices (
    price_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id  INTEGER NOT NULL,
    date        TEXT NOT NULL,                        -- ISO date 'YYYY-MM-DD'
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    adj_close   REAL,
    volume      INTEGER,
    FOREIGN KEY (company_id) REFERENCES companies (company_id),
    UNIQUE (company_id, date)                         -- prevents duplicate days
);
CREATE INDEX IF NOT EXISTS idx_prices_company_date
    ON stock_prices (company_id, date);

-- ---------------------------------------------------------------------------
-- financial_statements: periodic fundamentals (added Week 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_statements (
    statement_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id          INTEGER NOT NULL,
    period              TEXT NOT NULL,                -- e.g. '2025-Q1'
    period_end_date     TEXT,
    statement_type      TEXT NOT NULL,                -- income | balance | cashflow
    revenue             REAL,
    net_income          REAL,
    gross_profit        REAL,
    operating_income    REAL,
    total_assets        REAL,
    total_liabilities   REAL,
    total_equity        REAL,
    eps                 REAL,
    operating_cash_flow REAL,
    currency            TEXT,
    source              TEXT,
    FOREIGN KEY (company_id) REFERENCES companies (company_id),
    UNIQUE (company_id, period, statement_type)
);

-- ---------------------------------------------------------------------------
-- financial_ratios: computed metrics (added Week 2)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS financial_ratios (
    ratio_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id      INTEGER NOT NULL,
    period          TEXT,
    pe_ratio        REAL,
    profit_margin   REAL,
    current_ratio   REAL,
    debt_to_equity  REAL,
    roe             REAL,
    roa             REAL,
    quick_ratio     REAL,
    computed_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies (company_id),
    UNIQUE (company_id, period)
);

-- ---------------------------------------------------------------------------
-- news_articles: metadata only (no full copyrighted text). Added Week 4.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_articles (
    article_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id   INTEGER,                             -- NULL = market-wide
    headline     TEXT,
    summary      TEXT,
    source       TEXT,
    url          TEXT NOT NULL UNIQUE,                -- dedupe key
    published_at TEXT,
    fetched_at   TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (company_id) REFERENCES companies (company_id)
);
CREATE INDEX IF NOT EXISTS idx_news_published ON news_articles (published_at);

-- ---------------------------------------------------------------------------
-- sentiment_scores: derived sentiment (added Week 10)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sentiment_scores (
    sentiment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id      INTEGER,
    company_id      INTEGER,
    source_type     TEXT,                             -- news | reddit | stocktwits
    date            TEXT,
    sentiment_score REAL,                             -- -1.0 .. 1.0
    sentiment_label TEXT,                             -- positive | neutral | negative
    model_used      TEXT,
    FOREIGN KEY (article_id) REFERENCES news_articles (article_id),
    FOREIGN KEY (company_id) REFERENCES companies (company_id)
);

-- ---------------------------------------------------------------------------
-- users + watchlists: account features (added Week 9)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,                      -- never store plaintext
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS watchlists (
    watchlist_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    company_id   INTEGER NOT NULL,
    added_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users (user_id),
    FOREIGN KEY (company_id) REFERENCES companies (company_id),
    UNIQUE (user_id, company_id)
);

-- ---------------------------------------------------------------------------
-- update_logs: pipeline observability
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS update_logs (
    log_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT,
    source          TEXT,
    run_started_at  TEXT,
    run_finished_at TEXT,
    status          TEXT,                             -- success | partial | failed
    rows_added      INTEGER DEFAULT 0,
    rows_skipped    INTEGER DEFAULT 0,
    error_message   TEXT
);
