"""Price & news aggregation with layered fallbacks. All sources are FREE.

Price chain per symbol:
  yfinance -> Alpha Vantage (only if key present) -> deterministic simulation
News chain:
  official RSS feeds (feedparser) -> empty list (dashboard degrades, never 500)

Hardening: rotating User-Agents, optional outbound proxy, bounded timeouts,
bounded concurrency, and every symbol/region is validated upstream.
"""
from __future__ import annotations

import asyncio
import hashlib
import random
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import feedparser
import httpx
import pandas as pd
import yfinance as yf

from app.config import get_settings
from app.services import universe
from app.services.sentiment import analyze_sentiment
from app.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

MAX_SYMBOLS_PER_REGION = 12
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _headers() -> dict[str, str]:
    return {"User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9"}


def _client() -> httpx.Client:
    proxies = settings.proxy_url or None
    return httpx.Client(headers=_headers(), timeout=_TIMEOUT,
                        proxy=proxies, follow_redirects=True)


def _seed(symbol: str) -> random.Random:
    digest = hashlib.sha256(symbol.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


# ---------------------------------------------------------------------------
# Deterministic simulated history (fallback only; flagged `simulated=True`)
# ---------------------------------------------------------------------------

def simulate_history(symbol: str, days: int = 180,
                     base_price: float | None = None) -> list[dict]:
    rng = _seed(symbol)
    price = base_price or round(rng.uniform(15, 400), 2)
    rows: list[dict] = []
    day = datetime.now(timezone.utc) - timedelta(days=days)
    for _ in range(days):
        drift = rng.gauss(0.0004, 0.018)
        o = price
        c = max(1.0, round(price * (1 + drift), 4))
        h = max(o, c) * (1 + abs(rng.gauss(0, 0.006)))
        low = min(o, c) * (1 - abs(rng.gauss(0, 0.006)))
        rows.append({"time": day.strftime("%Y-%m-%d"), "open": round(o, 4),
                     "high": round(h, 4), "low": round(low, 4),
                     "close": c, "volume": int(rng.uniform(5e5, 4e7))})
        price = c
        day += timedelta(days=1)
    return rows


# ---------------------------------------------------------------------------
# Price fetchers
# ---------------------------------------------------------------------------

def fetch_yahoo_history(symbol: str, period: str = "6mo",
                        interval: str = "1d") -> list[dict] | None:
    try:
        ticker = yf.Ticker(symbol)
        frame: pd.DataFrame = ticker.history(period=period,
                                             interval=interval,
                                             auto_adjust=False)
        if frame is None or frame.empty:
            return None
        frame = frame.dropna(subset=["Close"])
        out: list[dict] = []
        for idx, row in frame.iterrows():
            out.append({"time": idx.strftime("%Y-%m-%d"),
                        "open": round(float(row["Open"]), 4),
                        "high": round(float(row["High"]), 4),
                        "low": round(float(row["Low"]), 4),
                        "close": round(float(row["Close"]), 4),
                        "volume": int(row.get("Volume", 0) or 0)})
        return out or None
    except Exception as exc:  # noqa: BLE001 - upstream flakiness expected
        log.warning("yahoo_fetch_failed", symbol=symbol, error=str(exc))
        return None


def fetch_alpha_vantage_history(symbol: str) -> list[dict] | None:
    if not settings.alpha_vantage_key:
        return None
    try:
        with _client() as client:
            resp = client.get(
                "https://www.alphavantage.co/query",
                params={"function": "TIME_SERIES_DAILY",
                        "symbol": symbol,
                        "outputsize": "compact",
                        "apikey": settings.alpha_vantage_key})
            resp.raise_for_status()
            payload = resp.json()
        series = payload.get("Time Series (Daily)") or {}
        rows = []
        for date, ohlc in sorted(series.items()):
            rows.append({"time": date,
                         "open": float(ohlc["1. open"]),
                         "high": float(ohlc["2. high"]),
                         "low": float(ohlc["3. low"]),
                         "close": float(ohlc["4. close"]),
                         "volume": int(ohlc["5. volume"])})
        return rows or None
    except Exception as exc:  # noqa: BLE001
        log.warning("alpha_vantage_fetch_failed", symbol=symbol,
                    error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Session freshness: never serve a chart that stops at an old session
# ---------------------------------------------------------------------------

MARKET_TZ = "America/New_York"


def _ny_now() -> datetime:
    """Current wall clock in US/Eastern (the reference session calendar).
    Falls back to a fixed UTC-4 approximation if the tz database is
    unavailable on the host."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(MARKET_TZ))
    except Exception:  # noqa: BLE001 - Windows hosts may lack tzdata
        return datetime.now(timezone.utc).astimezone(
            timezone(timedelta(hours=-4)))


def _session_date(now: datetime | None = None) -> str:
    """ISO date of the current (or most recent) weekday session.
    Weekends roll back to Friday."""
    now = now or _ny_now()
    day = now.date()
    while day.weekday() > 4:  # Sat/Sun -> Friday
        day -= timedelta(days=1)
    return day.isoformat()


def fetch_live_price(symbol: str) -> float | None:
    """Best-effort live/last traded price via yfinance ``fast_info``."""
    try:
        info = yf.Ticker(symbol).fast_info
        price = getattr(info, "last_price", None)
        if price is None:
            price = info["last_price"]  # mapping-style access
        return float(price) if price else None
    except Exception as exc:  # noqa: BLE001 - strictly best-effort
        log.warning("live_price_fetch_failed", symbol=symbol, error=str(exc))
        return None


def _top_up_forming_bar(symbol: str, bars: list[dict],
                        now: datetime | None = None) -> list[dict]:
    """Append the current session's forming candle when upstream daily
    history lags the live session.

    Why: Yahoo daily bars can lag the in-progress session (aggregation
    delay), leaving the chart parked on the previous close even while live
    ticks stream. Once today's session has started (>= 09:30 ET on a
    weekday) and a live price is obtainable, a forming bar is synthesized so
    the chart, ticker quotes and the Fear & Greed index all reflect the
    current session. Pre-open (and on weekends) the previous close IS the
    freshest real data, so bars stay untouched.
    """
    if not bars:
        return bars
    now = now or _ny_now()
    last_time = str(bars[-1].get("time", ""))
    # Only reason about real ISO dates; synthetic/test bars pass through.
    if len(last_time) != 10 or last_time[4] != "-":
        return bars
    session = _session_date(now)
    if last_time >= session:
        return bars  # already current
    if now.weekday() > 4 or (now.hour, now.minute) < (9, 30):
        return bars  # weekend / pre-open: previous close is correct
    price = fetch_live_price(symbol)
    if not price or price <= 0:
        return bars  # no live data — serve history as-is
    prev_close = bars[-1].get("close") or price
    log.info("forming_bar_appended", symbol=symbol, session=session,
             price=price)
    return bars + [{"time": session, "open": prev_close,
                    "high": max(prev_close, price),
                    "low": min(prev_close, price),
                    "close": price, "volume": 0}]


def fetch_history(symbol: str, region: str = "US",
                  period: str = "6mo") -> tuple[list[dict], bool]:
    """Layered fallback chain. Returns (bars, simulated)."""
    for provider in (fetch_yahoo_history, fetch_alpha_vantage_history):
        rows = provider(symbol)
        if rows:
            return _top_up_forming_bar(symbol, rows), False
    log.warning("falling_back_to_simulation", symbol=symbol,
                region=region)
    return simulate_history(symbol), True


def latest_quote(symbol: str, region: str, name: str = "") -> dict:
    """Single snapshot quote used by the live ticker."""
    bars, simulated = fetch_history(symbol, region)
    last = bars[-1]
    prev = bars[-2] if len(bars) > 1 else last
    change = round(last["close"] - prev["close"], 4)
    pct = round(change / prev["close"] * 100, 2) if prev["close"] else 0.0
    return {"symbol": symbol, "name": name or universe.DISPLAY_NAMES.get(
        symbol, symbol), "price": last["close"], "change": change,
        "change_percent": pct, "volume": last.get("volume", 0),
        "simulated": simulated}


def quotes_for_region(region: str) -> list[dict]:
    symbols = universe.stocks_for(region)[:MAX_SYMBOLS_PER_REGION]
    loop = asyncio.new_event_loop()
    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(
                lambda s: latest_quote(s, region), symbols))
        return results
    finally:
        loop.close()

# ---------------------------------------------------------------------------
# News aggregation via official RSS feeds
# ---------------------------------------------------------------------------


MAX_NEWS_AGE = timedelta(days=7)


def _parse_rss(xml_bytes: bytes, source: str) -> list[dict]:
    parsed = feedparser.parse(xml_bytes)
    items: list[dict] = []
    now = datetime.now(timezone.utc)
    for entry in parsed.entries[:20]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        if not title or not link or not re.match(r"^https?://", link):
            continue
        published_raw = getattr(entry, "published_parsed", None)
        try:
            published = (datetime(*published_raw[:6], tzinfo=timezone.utc)
                         if published_raw else now)
        except Exception:  # noqa: BLE001
            published = now
        # Freshness gate: never ingest headlines older than 7 days.
        if now - published > MAX_NEWS_AGE:
            continue
        summary = re.sub(r"<[^>]+>", "", getattr(entry, "summary", ""))[:400]
        label, score = analyze_sentiment(f"{title}. {summary}")
        items.append({"url": link[:1000], "title": title[:500],
                      "summary": summary, "source": source,
                      "sentiment_label": label,
                      "sentiment_score": score,
                      "published_at": published})
    return items


def fetch_news(region: str = "GLOBAL",
               limit: int = 30) -> list[dict]:
    feeds = universe.NEWS_FEEDS.get(region, universe.NEWS_FEEDS["GLOBAL"])
    collected: list[dict] = []
    seen: set[str] = set()
    with _client() as client:
        for feed_url, source in feeds:
            if len(collected) >= limit:
                break
            try:
                resp = client.get(feed_url)
                if resp.status_code != 200:
                    log.warning("rss_fetch_failed", url=feed_url,
                                status=resp.status_code)
                    continue
                for item in _parse_rss(resp.content, source):
                    if item["url"] in seen:
                        continue
                    seen.add(item["url"])
                    item["region"] = region
                    collected.append(item)
            except Exception as exc:  # noqa: BLE001
                log.warning("rss_feed_error", url=feed_url, error=str(exc))
    return collected[:limit]
