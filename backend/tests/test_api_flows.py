"""API-flow tests: market endpoints (network mocked), news, auth
refresh-rotation lifecycle, migration entrypoint, and beat schedule."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database import SessionLocal
from app.models import NewsArticle, Prediction


@pytest.fixture(autouse=True)
def _clear_market_cache():
    from app.routers import market as market_router
    market_router._cache.clear()
    yield
    market_router._cache.clear()


def _quote(symbol: str, change_percent: float, volume: int) -> dict:
    return {"symbol": symbol, "name": symbol, "price": 100.0,
            "change": change_percent, "change_percent": change_percent,
            "volume": volume, "simulated": True}


class TestMarketEndpoints:
    def test_regions(self, client):
        body = client.get("/api/market/regions").json()["data"]
        assert "US" in body["regions"] and "IN" in body["regions"]
        assert "NP" not in body["regions"]
        assert body["indices"]["US"]["symbol"] == "^GSPC"

    def test_movers_ranking(self, client, monkeypatch):
        monkeypatch.setattr("app.routers.market._quotes_sync", lambda region: [
            _quote("AAA", 5.0, 1_000),
            _quote("BBB", -3.0, 9_000),
            _quote("CCC", 1.0, 50_000),
        ])
        data = client.get("/api/market/movers?region=US").json()["data"]
        assert data["gainers"][0]["symbol"] == "AAA"
        assert data["losers"][0]["symbol"] == "BBB"
        assert data["most_active"][0]["symbol"] == "CCC"

    def test_invalid_region_rejected(self, client):
        resp = client.get("/api/market/movers?region=MARS")
        assert resp.status_code == 422

    def test_history_mocked(self, client, monkeypatch, sample_bars):
        monkeypatch.setattr(
            "app.services.scraper.fetch_history",
            lambda sym, region="US", period="6mo": (sample_bars[:60], False))
        data = client.get("/api/market/history/NVDA?region=US").json()["data"]
        assert len(data["bars"]) == 60
        assert data["simulated"] is False

    def test_search_matches_symbols_and_indices(self, client):
        hits = client.get("/api/market/search",
                          params={"q": "nvda"}).json()["data"]
        assert any(h["symbol"] == "NVDA" for h in hits)
        index_hits = client.get("/api/market/search",
                                params={"q": "nifty"}).json()["data"]
        assert any("^NSEI" == h["symbol"] for h in index_hits)

    def test_fear_greed_shape(self, client, monkeypatch, sample_bars):
        monkeypatch.setattr(
            "app.services.scraper.fetch_history",
            lambda sym, region="US", period="6mo": (sample_bars, True))
        data = client.get("/api/market/fear-greed").json()["data"]
        assert 0 <= data["score"] <= 100
        assert data["label"]

    def test_predictions_from_seeded_db(self, client):
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(Prediction(symbol="NVDA", region="US", prob_up=0.7,
                              recommendation="BUY", breakout_score=88,
                              volume_trend_3d=25.0, sentiment_score=0.4,
                              computed_at=now))
            db.commit()
        data = client.get("/api/market/predictions?region=US").json()["data"]
        assert len(data) == 1
        assert data[0]["recommendation"] == "BUY"

    def test_underdogs_filters_low_scores(self, client):
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(Prediction(symbol="HOT", region="US", prob_up=0.8,
                              recommendation="BUY", breakout_score=92,
                              computed_at=now))
            db.add(Prediction(symbol="COLD", region="US", prob_up=0.2,
                              recommendation="SELL", breakout_score=10,
                              computed_at=now))
            db.commit()
        data = client.get("/api/market/underdogs?region=US").json()["data"]
        symbols = [p["symbol"] for p in data]
        assert "HOT" in symbols and "COLD" not in symbols


class TestNewsEndpoint:
    def test_news_from_db(self, client):
        with SessionLocal() as db:
            db.add(NewsArticle(
                url="https://example.com/a1", title="Markets rally hard",
                source="TestWire", region="US",
                sentiment_label="BULLISH", sentiment_score=0.5,
                published_at=datetime.now(timezone.utc)))
            db.commit()
        items = client.get("/api/news?region=US").json()["data"]
        assert items[0]["sentiment_label"] == "BULLISH"

    def test_news_never_serves_stale_headlines(self, client):
        """Freshness policy: <=72h is served; anything older than the
        hard 7-day cap must never reach the UI."""
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            db.add(NewsArticle(
                url="https://example.com/fresh", title="Fresh headline",
                source="TestWire", region="US",
                sentiment_label="BULLISH", sentiment_score=0.4,
                published_at=now - timedelta(hours=12)))
            db.add(NewsArticle(
                url="https://example.com/recent", title="Recent headline",
                source="TestWire", region="US",
                sentiment_label="NEUTRAL", sentiment_score=0.0,
                published_at=now - timedelta(days=2)))
            db.add(NewsArticle(
                url="https://example.com/stale", title="Ancient headline",
                source="TestWire", region="US",
                sentiment_label="BEARISH", sentiment_score=-0.3,
                published_at=now - timedelta(days=10)))
            db.commit()
        items = client.get("/api/news?region=US").json()["data"]
        urls = [i["url"] for i in items]
        assert "https://example.com/fresh" in urls
        assert "https://example.com/recent" in urls
        assert "https://example.com/stale" not in urls


class TestAuthLifecycle:
    def test_refresh_rotation_and_logout(self, client):
        reg = client.post("/api/auth/register", json={
            "email": "life@orion.io", "username": "lifecycle",
            "password": "Sup3rSecret99"})
        assert reg.status_code == 200

        # Cookie jar holds the HttpOnly refresh token.
        refreshed = client.post("/api/auth/refresh")
        assert refreshed.status_code == 200
        new_access = refreshed.json()["data"]["access_token"]
        assert new_access

        me = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {new_access}"})
        assert me.status_code == 200
        assert me.json()["data"]["username"] == "lifecycle"

        # Rotation must mark the consumed token as revoked server-side.
        from app.models import RefreshTokenRecord
        with SessionLocal() as db:
            revoked_count = db.query(RefreshTokenRecord).filter_by(
                user_id=1, revoked=True).count()
        assert revoked_count >= 1

        logout = client.post("/api/auth/logout", headers={
            "Authorization": f"Bearer {new_access}"})
        assert logout.status_code == 200


class TestOps:
    def test_beat_schedule_registered(self):
        from app.celery_app import celery
        names = {cfg["task"] for cfg in celery.conf.beat_schedule.values()}
        assert names == {"orion.ingest_prices", "orion.ingest_news",
                         "orion.compute_predictions"}

    def test_db_migrate_entrypoint_succeeds(self):
        from app.db_migrate import main
        assert main() == 0

    def test_healthz(self, client):
        assert client.get("/healthz").status_code == 200
