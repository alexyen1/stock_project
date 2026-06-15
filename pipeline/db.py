"""Database helpers: connection, schema setup, and SQL dialect adapters."""
import sqlite3
from contextlib import contextmanager

import config


def is_postgres() -> bool:
    return bool(config.DATABASE_URL)


def adapt_sql(sql: str) -> str:
    """Swap ? → %s placeholders when targeting Postgres."""
    if is_postgres():
        return sql.replace("?", "%s")
    return sql


def get_connection():
    """Open a database connection (Postgres if DATABASE_URL is set, else SQLite)."""
    if is_postgres():
        import psycopg2
        return psycopg2.connect(config.DATABASE_URL)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@contextmanager
def db_cursor():
    """Yield a cursor, commit on success, roll back on error, always close."""
    conn = get_connection()
    try:
        if is_postgres():
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        else:
            cur = conn.cursor()
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create all tables from the appropriate schema file (idempotent)."""
    if is_postgres():
        with open(config.SCHEMA_POSTGRES_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(schema_sql)
            conn.commit()
        finally:
            conn.close()
    else:
        with open(config.SCHEMA_PATH, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn = get_connection()
        try:
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()
