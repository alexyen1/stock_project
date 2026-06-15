"""Central configuration for Market Lens."""
import os
from pathlib import Path

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "market_lens.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"
SCHEMA_POSTGRES_PATH = BASE_DIR / "db" / "schema_postgres.sql"

# --- Database URL ----------------------------------------------------------
# On Streamlit Cloud and GitHub Actions, DATABASE_URL is injected as an env
# var. Locally, load it from .streamlit/secrets.toml so plain Python scripts
# (like ingest_prices) also target Postgres without any extra setup.
if "DATABASE_URL" not in os.environ:
    _secrets_path = BASE_DIR / ".streamlit" / "secrets.toml"
    if _secrets_path.exists():
        import tomllib
        with open(_secrets_path, "rb") as _f:
            _secrets = tomllib.load(_f)
        if "DATABASE_URL" in _secrets:
            os.environ["DATABASE_URL"] = _secrets["DATABASE_URL"]

DATABASE_URL: str | None = os.environ.get("DATABASE_URL")

# --- What to track ---------------------------------------------------------
# Edit this list to change which companies the pipeline ingests.
TICKERS = [
    "AAPL",   # Apple
    "MSFT",   # Microsoft
    "GOOGL",  # Alphabet
    "AMZN",   # Amazon
    "NVDA",   # NVIDIA
    "TSLA",   # Tesla
    "JPM",    # JPMorgan Chase
    "JNJ",    # Johnson & Johnson
    "XOM",    # Exxon Mobil
    "WMT",    # Walmart
]

# How much price history to pull on each run (yfinance period string).
PRICE_PERIOD = "1y"   # "1mo", "6mo", "1y", "5y", "max"

# Make sure the data directory exists.
DATA_DIR.mkdir(parents=True, exist_ok=True)
