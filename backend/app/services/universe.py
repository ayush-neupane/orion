"""Tradable universe per region + RSS news feed registry.

Market data sources are 100% FREE:
- US/EU/UK/JP/IN: Yahoo Finance via yfinance (no key required), with a
  deterministic simulated fallback so the dashboard is never empty.
"""
from __future__ import annotations

REGIONS: list[str] = ["GLOBAL", "US", "UK", "EU", "JP", "IN"]

UNIVERSE: dict[str, dict] = {
    "US": {"index": ("^GSPC", "S&P 500"),
           "stocks": ["AAPL", "MSFT", "NVDA", "GOOGL", "TSLA", "AMZN",
                      "META", "AMD", "NFLX", "JPM"]},
    "UK": {"index": ("^FTSE", "FTSE 100"),
           "stocks": ["HSBA.L", "SHEL.L", "BP.L", "AZN.L", "ULVR.L",
                      "GSK.L", "HSX.L"]},
    "EU": {"index": ("^STOXX50E", "Euro Stoxx 50"),
           "stocks": ["ASML.AS", "SAP.DE", "SIE.DE", "MC.PA", "OR.PA",
                      "ALV.DE"]},
    "JP": {"index": ("^N225", "Nikkei 225"),
           "stocks": ["7203.T", "6758.T", "6501.T", "9432.T", "8306.T"]},
    "IN": {"index": ("^NSEI", "NIFTY 50"),
           "stocks": ["RELIANCE.NS", "TCS.NS", "INFY.NS", "HDFCBANK.NS",
                      "ICICIBANK.NS", "SBIN.NS"]},
}

DISPLAY_NAMES: dict[str, str] = {
    "^GSPC": "S&P 500", "^FTSE": "FTSE 100", "^STOXX50E": "Euro Stoxx 50",
    "^N225": "Nikkei 225", "^NSEI": "NIFTY 50",
}

# RSS feeds per region - all free, official publisher feeds. Bloomberg and
# Reuters prohibit headless site scraping, so we consume their *official*
# RSS endpoints instead (compliant alternative, same content).
NEWS_FEEDS: dict[str, list[tuple[str, str]]] = {
    "GLOBAL": [
        ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "WSJ Markets"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
        ("https://www.seekingalpha.com/feed.xml", "Seeking Alpha"),
        ("https://feeds.content.dowjones.io/public/rss/mw_topstories",
         "MarketWatch"),
    ],
    "US": [
        ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "WSJ Markets"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
    ],
    "UK": [
        ("https://www.ft.com/markets?format=rss", "Financial Times"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
    ],
    "EU": [
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
        ("https://www.euronews.com/rss?level=theme&name=business",
         "Euronews Business"),
    ],
    "JP": [
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
    ],
    "IN": [
        ("https://www.businesstoday.in/rssfeeds/?id=home", "Business Today"),
        ("https://finance.yahoo.com/news/rssindex", "Yahoo Finance"),
    ],
}


def stocks_for(region: str) -> list[str]:
    if region == "GLOBAL":
        merged: list[str] = []
        for cfg in UNIVERSE.values():
            merged.extend(cfg["stocks"])
        return merged
    return UNIVERSE.get(region, {}).get("stocks", [])


def index_for(region: str) -> tuple[str, str]:
    return UNIVERSE.get(region, UNIVERSE["US"])["index"]
