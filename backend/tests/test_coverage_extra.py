"""Focused coverage: scraper providers (respx-mocked),
inline prediction cold-start, and WebSocket manager internals."""
from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.services import scraper


class TestAlphaVantage:
    @respx.mock
    def test_parses_daily_series(self, monkeypatch, settings_av_key):
        payload = {
            "Time Series (Daily)": {
                "2025-01-02": {"1. open": "10", "2. high": "11",
                               "3. low": "9.5", "4. close": "10.5",
                               "5. volume": "12345"},
                "2025-01-03": {"1. open": "10.5", "2. high": "12",
                               "3. low": "10.4", "4. close": "11.8",
                               "5. volume": "23456"},
            }
        }
        respx.get("https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(200, json=payload))
        rows = scraper.fetch_alpha_vantage_history("AAPL")
        assert rows and rows[-1]["close"] == 11.8

    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(scraper.settings, "alpha_vantage_key", "")
        assert scraper.fetch_alpha_vantage_history("AAPL") is None

    @respx.mock
    def test_http_error_returns_none(self, settings_av_key):
        respx.get("https://www.alphavantage.co/query").mock(
            return_value=httpx.Response(429, json={}))
        assert scraper.fetch_alpha_vantage_history("AAPL") is None


@pytest.fixture()
def settings_av_key(monkeypatch):
    monkeypatch.setattr(scraper.settings, "alpha_vantage_key", "test-key-0")


class TestYahoo:
    def test_failure_returns_none(self, monkeypatch):
        def boom(*a, **kw):
            raise RuntimeError("network down")
        monkeypatch.setattr(scraper.yf, "Ticker", boom)
        assert scraper.fetch_yahoo_history("AAPL") is None

    def test_empty_frame_returns_none(self, monkeypatch):
        class FakeTicker:
            def history(self, **kwargs):
                import pandas as pd
                return pd.DataFrame()

        monkeypatch.setattr(scraper.yf, "Ticker", lambda sym: FakeTicker())
        assert scraper.fetch_yahoo_history("AAPL") is None


class TestInlineColdStart:
    def test_compute_inline_persists_and_ranks(self, client, monkeypatch,
                                               sample_bars):
        from app.routers.market import _compute_inline
        monkeypatch.setattr(
            "app.services.scraper.fetch_history",
            lambda sym, region="US", period="6mo": (sample_bars, True))
        out = _compute_inline("US")
        assert out
        assert all(1 <= p["breakout_score"] <= 100 for p in out)
        scores = [p["breakout_score"] for p in out]
        assert scores == sorted(scores, reverse=True)

    def test_predictions_endpoint_cold_start(self, client, monkeypatch,
                                             sample_bars):
        monkeypatch.setattr(
            "app.services.scraper.fetch_history",
            lambda sym, region="US", period="6mo": (sample_bars, True))
        data = client.get("/api/market/predictions?region=US").json()["data"]
        assert len(data) > 0


class TestWsManager:
    def test_move_room_and_counts(self):
        from app.websocket_manager import ConnectionManager

        async def scenario():
            mgr = ConnectionManager()

            class FakeWS:
                def __init__(self):
                    self.sent = []

                async def send_text(self, msg):
                    self.sent.append(msg)

            ws = FakeWS()
            # connect() accepts a real WebSocket; bypass accept by direct add.
            mgr._rooms.setdefault("US", set()).add(ws)
            mgr.move_room(ws, "US", "IN")
            assert mgr.room_size("IN") == 1
            assert mgr.room_size("US") == 0
            await mgr.broadcast("IN", {"event": "tick"})
            assert len(ws.sent) == 1

            dead = FakeWS()

            async def explode(msg):
                raise RuntimeError("closed")

            dead.send_text = explode
            mgr._rooms.setdefault("IN", set()).add(dead)
            await mgr.broadcast("IN", {"event": "tick"})  # prunes dead socket
            assert mgr.room_size("IN") == 1

        asyncio.run(scenario())
