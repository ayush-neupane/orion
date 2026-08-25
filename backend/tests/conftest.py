"""Shared pytest fixtures. Runs the full app against an in-memory SQLite DB
with a deterministic secret; external network calls are mocked in tests."""
from __future__ import annotations

import os

os.environ.update(
    ENVIRONMENT="test",
    SECRET_KEY="test-secret-key-not-for-production-0123456789abcdef",
    DATABASE_URL="sqlite:///./orion_test.db",
    RATELIMIT_STORAGE_URI="memory://",
    LOG_FILE="logs/orion_test.log",
    COOKIE_SECURE="false",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Isolate the in-memory rate-limit counters between tests."""
    yield
    from app.middleware.security import limiter
    try:
        limiter.reset()
    except Exception:  # noqa: BLE001 - best effort cleanup only
        pass


@pytest.fixture(autouse=True)
def _db():
    """Fresh schema per test. Dispose pooled connections BEFORE touching the
    SQLite file - Windows locks files with open handles."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def client() -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(client: TestClient) -> dict[str, str]:
    payload = {"email": "trader@orion.io", "username": "trader_one",
               "password": "Sup3rSecret99"}
    resp = client.post("/api/auth/register", json=payload)
    assert resp.status_code == 200, resp.text
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_bars() -> list[dict]:
    import math

    bars = []
    price = 100.0
    for i in range(120):
        day_index = 17_000 + i
        drift = 0.4 * math.sin(i / 7) + (0.15 if i % 3 else -0.1)
        open_p = round(price, 2)
        close_p = round(max(5.0, price + drift), 2)
        bars.append({"time": str(day_index), "open": open_p,
                     "high": round(max(open_p, close_p) * 1.01, 2),
                     "low": round(min(open_p, close_p) * 0.99, 2),
                     "close": close_p,
                     "volume": int(1_000_000 + i * 10_000)})
        price = close_p
    # Replace synthetic time indices with real dates for realism.
    from datetime import date, timedelta
    start = date(2025, 1, 1)
    for i, bar in enumerate(bars):
        bar["time"] = (start + timedelta(days=i)).isoformat()
    return bars


@pytest.fixture(scope="session", autouse=True)
def _eager_celery():
    from app.celery_app import celery
    celery.conf.task_always_eager = True
    celery.conf.broker_url = "memory://"
    celery.conf.result_backend = "cache+memory://"
    yield
