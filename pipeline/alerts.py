"""Price-alert helpers — create, list, delete, and evaluate threshold alerts.

Alerts are evaluated live against the latest cached price whenever a company
page loads. There's no background job or push channel — this just answers
"is any alert for this ticker currently true?" on each render.
"""
from pipeline.db import adapt_sql, db_cursor

VALID_DIRECTIONS = ("above", "below")


def create_alert(ticker: str, direction: str, threshold_price: float) -> dict:
    """Create a price alert for one ticker. direction is 'above' or 'below'."""
    ticker = ticker.upper().strip()
    if direction not in VALID_DIRECTIONS:
        return {"success": False, "error": "Invalid alert direction."}
    if threshold_price is None or threshold_price <= 0:
        return {"success": False, "error": "Threshold price must be greater than 0."}
    try:
        with db_cursor() as cur:
            cur.execute(adapt_sql("SELECT company_id FROM companies WHERE ticker = ?"), (ticker,))
            row = cur.fetchone()
            if not row:
                return {"success": False, "error": f"'{ticker}' is not tracked."}
            cur.execute(
                adapt_sql("""
                INSERT INTO alerts (company_id, direction, threshold_price)
                VALUES (?, ?, ?)
                """),
                (row["company_id"], direction, threshold_price),
            )
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def list_alerts(ticker: str) -> list[dict]:
    """All alerts set for one ticker, newest first."""
    ticker = ticker.upper().strip()
    with db_cursor() as cur:
        cur.execute(
            adapt_sql("""
            SELECT a.alert_id, a.direction, a.threshold_price, a.created_at
            FROM alerts a
            JOIN companies c ON c.company_id = a.company_id
            WHERE c.ticker = ?
            ORDER BY a.alert_id DESC
            """),
            (ticker,),
        )
        return [dict(r) for r in cur.fetchall()]


def delete_alert(alert_id: int) -> dict:
    try:
        with db_cursor() as cur:
            cur.execute(adapt_sql("DELETE FROM alerts WHERE alert_id = ?"), (alert_id,))
        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def triggered_alerts(alerts: list[dict], latest_price: float) -> list[dict]:
    """Filter alerts whose threshold currently holds against latest_price."""
    hits = []
    for a in alerts:
        if a["direction"] == "above" and latest_price >= a["threshold_price"]:
            hits.append(a)
        elif a["direction"] == "below" and latest_price <= a["threshold_price"]:
            hits.append(a)
    return hits
