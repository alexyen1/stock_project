"""Database helpers: connection and schema setup."""
import sqlite3
from contextlib import contextmanager

import config


def get_connection():
    """Open a SQLite connection with sensible defaults."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_cursor():
    """Context manager that commits on success and rolls back on error."""
    conn = get_connection()
    try:
        yield conn.cursor()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables from db/schema.sql (idempotent)."""
    with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
