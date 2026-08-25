"""Integration tests with mocked external HTTP (respx for httpx) and
eager Celery tasks against the real (SQLite) database."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import respx

from app.services import scraper
from app.services.sentiment import analyze_sentiment


def _rss_pubdate(hours_ago: int) -> str:
    """RFC-2822 pubDate a fixed number of hours in the past, so the
    sample always satisfies ORION's 7-day news freshness gate."""
    dt = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return format_datetime(dt)


RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>T</title>
<item>
  <title>Markets surge as tech giants beat earnings expectations</title>
  <link>https://example.com/news/1</link>
  <description>Strong profits and growth drive a rally.</description>
  <pubDate>{h1}</pubDate>
</item>
<item>
  <title>Shares plunge after fraud investigation probe announced</title>
  <link>https://example.com/news/2</link>
  <description>Investors fear heavy losses ahead.</description>
  <pubDate>{h2}</pubDate>
</item>
</channel></rss>""".replace(b"{h1}", _rss_pubdate(2).encode()).replace(
    b"{h2}", _rss_pubdate(3).encode())


class TestSentiment:
    def test_bullish_lexicon(self):
        label, score = analyze_sentiment(
            "Stocks surge and rally on record profits")
        assert label == "BULLISH"
        assert score > 0

    def test_bearish_lexicon(self):
        label, score = analyze_sentiment(
            "Shares plunge amid fraud probe and losses")
        assert label == "BEARISH"
        assert score < 0

    def test_neutral(self):
        label, score = analyze_sentiment(
            "The company announced a meeting schedule")
        assert label == "NEUTRAL"

    def test_negation_flips(self):
        positive = analyze_sentiment("Analysts are bullish on outlook")[1]
        negated = analyze_sentiment("Analysts are not bullish on outlook")[1]
        assert negated < positive

    def test_empty_is_neutral(self):
        assert analyze_sentiment("") == ("NEUTRAL", 0.0)


class TestScraperFallbacks:
    def test_simulation_is_deterministic(self):
        a = scraper.simulate_history("NVDA")
        b = scraper.simulate_history("NVDA")
        assert a == b
        assert len(a) == 180
        assert all(bar["low"] <= bar["close"] <= bar["high"] for bar in a[:50])

    @respx.mock
    def test_rss_parsing_and_sentiment(self):
        respx.get(url__startswith="https://feeds.example.com/").mock(
            return_value=httpx.Response(200, content=RSS_SAMPLE))
        from app.services import universe
        original = universe.NEWS_FEEDS["GLOBAL"]
        universe.NEWS_FEEDS["GLOBAL"] = [
            ("https://feeds.example.com/rss.xml", "ExampleWire")]
        try:
            items = scraper.fetch_news("GLOBAL", limit=10)
        finally:
            universe.NEWS_FEEDS["GLOBAL"] = original
        assert len(items) == 2
        labels = {item["sentiment_label"] for item in items}
        assert "BULLISH" in labels and "BEARISH" in labels

    @respx.mock
    def test_rss_failure_returns_empty_not_raise(self):
        respx.get(url__startswith="https://broken.example.com/").mock(
            return_value=httpx.Response(500))
        from app.services import universe
        original = universe.NEWS_FEEDS["GLOBAL"]
        universe.NEWS_FEEDS["GLOBAL"] = [
            ("https://broken.example.com/rss.xml", "Broken")]
        try:
            assert scraper.fetch_news("GLOBAL") == []
        finally:
            universe.NEWS_FEEDS["GLOBAL"] = original

    def test_history_chain_falls_back_to_simulation(self, monkeypatch):
        monkeypatch.setattr(scraper, "fetch_yahoo_history",
                            lambda *a, **kw: None)
        monkeypatch.setattr(scraper, "fetch_alpha_vantage_history",
                            lambda *a, **kw: None)
        bars, simulated = scraper.fetch_history("FAKE.SYM", "US")
        assert simulated is True
        assert len(bars) > 30

    # ------------------------------------------------------------------
    # Session freshness: forming-bar top-up for lagging daily feeds
    # ------------------------------------------------------------------

    @staticmethod
    def _stale_bars() -> list[dict]:
        return [{"time": "2026-08-21", "open": 100.0, "high": 102.0,
                 "low": 99.0, "close": 101.0, "volume": 1_000}]

    def test_forming_bar_appended_during_session(self, monkeypatch):
        from zoneinfo import ZoneInfo
        # Monday 2026-08-24, 10:00 US/Eastern — session in progress.
        now = datetime(2026, 8, 24, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        monkeypatch.setattr(scraper, "fetch_live_price",
                            lambda sym: 105.5)
        bars = scraper._top_up_forming_bar("META", self._stale_bars(), now)
        assert len(bars) == 2
        forming = bars[-1]
        assert forming["time"] == "2026-08-24"
        assert forming["open"] == 101.0
        assert forming["close"] == 105.5
        assert forming["high"] == 105.5
        assert forming["low"] == 101.0

    def test_no_top_up_before_open(self, monkeypatch):
        from zoneinfo import ZoneInfo
        # Monday 08:00 ET — pre-open; previous close is the freshest data.
        now = datetime(2026, 8, 24, 8, 0, tzinfo=ZoneInfo("America/New_York"))
        called = {"n": 0}

        def _no_fetch(sym):
            called["n"] += 1
            return 105.5

        monkeypatch.setattr(scraper, "fetch_live_price", _no_fetch)
        bars = scraper._top_up_forming_bar("META", self._stale_bars(), now)
        assert len(bars) == 1
        assert called["n"] == 0

    def test_no_top_up_when_already_current(self, monkeypatch):
        from zoneinfo import ZoneInfo
        now = datetime(2026, 8, 24, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        monkeypatch.setattr(scraper, "fetch_live_price",
                            lambda sym: 105.5)
        bars = scraper._top_up_forming_bar(
            "META", [{"time": "2026-08-24", "open": 100.0, "high": 103.0,
                      "low": 99.0, "close": 102.0, "volume": 1_000}], now)
        assert len(bars) == 1

    def test_no_top_up_without_live_price(self, monkeypatch):
        from zoneinfo import ZoneInfo
        now = datetime(2026, 8, 24, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        monkeypatch.setattr(scraper, "fetch_live_price",
                            lambda sym: None)
        bars = scraper._top_up_forming_bar("META", self._stale_bars(), now)
        assert len(bars) == 1

    def test_non_iso_bars_pass_through(self, monkeypatch):
        from zoneinfo import ZoneInfo
        now = datetime(2026, 8, 24, 10, 0, tzinfo=ZoneInfo("America/New_York"))
        monkeypatch.setattr(scraper, "fetch_live_price",
                            lambda sym: 105.5)
        synthetic = [{"time": "17000", "open": 1.0, "high": 1.0, "low": 1.0,
                      "close": 1.0, "volume": 0}]
        assert scraper._top_up_forming_bar("X", synthetic, now) == synthetic

    def test_fetch_history_tops_up_real_rows(self, monkeypatch):
        monkeypatch.setattr(scraper, "fetch_yahoo_history",
                            lambda *a, **kw: self._stale_bars())
        monkeypatch.setattr(scraper, "fetch_alpha_vantage_history",
                            lambda *a, **kw: None)
        monkeypatch.setattr(scraper, "fetch_live_price", lambda sym: 105.5)
        bars, simulated = scraper.fetch_history("META", "US")
        assert simulated is False
        assert bars[-1]["time"] == scraper._session_date() or \
            len(bars) == 2  # appended when a session is in progress


class TestCeleryPipelineE2E:
    def test_ingest_then_predict(self, monkeypatch):
        from app.celery_app import compute_predictions, ingest_prices
        monkeypatch.setattr(scraper, "fetch_history",
                            lambda sym, region, period="6mo":
                            (scraper.simulate_history(sym), True))
        ingest_prices_result = ingest_prices.apply().get()
        assert ingest_prices_result.get("rows_inserted", 0) > 0
        predict_result = compute_predictions.apply().get()
        assert predict_result.get("computed", 0) > 0

        from app.database import SessionLocal
        from app.models import Prediction
        with SessionLocal() as db:
            rows = db.query(Prediction).all()
            assert rows
            for row in rows:
                assert 0 <= row.prob_up <= 1
                assert row.recommendation in {"BUY", "HOLD", "SELL"}
                assert 1 <= row.breakout_score <= 100

    def test_ingest_prices_is_idempotent(self, monkeypatch):
        from app.celery_app import ingest_prices
        monkeypatch.setattr(scraper, "fetch_history",
                            lambda sym, region, period="6mo":
                            (scraper.simulate_history(sym, days=60), True))
        first = ingest_prices.apply().get()
        second = ingest_prices.apply().get()
        # Second identical run must insert nothing new.
        assert second.get("rows_inserted", 0) == 0
        assert first.get("rows_inserted", 0) > 0
