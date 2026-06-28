"""News aggregation — combines yfinance per-ticker news with Google News RSS.

Fetched live (the app caches results for a few minutes) rather than stored
in the database, so headlines stay current without a daily ingestion job.
Neither source requires an API key.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests
import yfinance as yf

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _parse_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalize_yf_entry(entry: dict) -> dict | None:
    # yfinance has shipped at least two news payload shapes; handle both.
    content = entry.get("content") if isinstance(entry.get("content"), dict) else entry

    headline = content.get("title")
    if not headline:
        return None

    url = None
    for key in ("clickThroughUrl", "canonicalUrl"):
        candidate = content.get(key)
        if isinstance(candidate, dict) and candidate.get("url"):
            url = candidate["url"]
            break
    url = url or content.get("link")
    if not url:
        return None

    provider = content.get("provider")
    source = provider.get("displayName") if isinstance(provider, dict) else content.get("publisher")

    return {
        "headline": headline,
        "summary": content.get("summary") or content.get("description") or "",
        "source": source or "Yahoo Finance",
        "url": url,
        "published_at": _parse_timestamp(content.get("pubDate") or content.get("providerPublishTime")),
    }


def _from_yfinance(ticker: str) -> list[dict]:
    try:
        raw = yf.Ticker(ticker).news or []
    except Exception:
        raw = []
    items = (_normalize_yf_entry(entry) for entry in raw)
    return [item for item in items if item]


def _from_google_rss(query: str, limit: int = 15) -> list[dict]:
    url = GOOGLE_NEWS_RSS.format(query=quote(query))
    try:
        resp = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    items = []
    for item in root.findall("./channel/item")[:limit]:
        link = item.findtext("link")
        if not link:
            continue
        title = (item.findtext("title") or "").strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else "Google News"
        if title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")].strip()

        pub_date = item.findtext("pubDate")
        try:
            published_at = parsedate_to_datetime(pub_date) if pub_date else None
        except (TypeError, ValueError):
            published_at = None

        items.append({
            "headline": title,
            "summary": "",
            "source": source,
            "url": link,
            "published_at": published_at,
        })
    return items


def get_news(ticker: str, company_name: str | None = None, limit: int = 20) -> list[dict]:
    """Recent news for a ticker, combined from yfinance and Google News RSS.

    Deduplicated by URL, sorted newest first. Each item has keys:
    headline, summary, source, url, published_at (datetime or None).
    """
    query = company_name or ticker
    items = _from_yfinance(ticker) + _from_google_rss(f"{query} stock")

    seen = set()
    deduped = []
    for item in items:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        deduped.append(item)

    deduped.sort(key=lambda it: it["published_at"] or _EPOCH, reverse=True)
    return deduped[:limit]
