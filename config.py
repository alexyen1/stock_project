"""Central configuration for Market Lens."""
from pathlib import Path

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "market_lens.db"
SCHEMA_PATH = BASE_DIR / "db" / "schema.sql"

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
