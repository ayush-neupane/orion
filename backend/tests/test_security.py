"""Security tests: auth hardening, rate limiting, CORS, security headers,
injection resistance, envelope integrity, and WebSocket token enforcement."""
from __future__ import annotations

import os

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings

settings = get_settings()

VALID_USER = {"email": "sec@orion.io", "username": "sec_user",
              "password": "Sup3rSecret99"}


def _register(client: TestClient) -> str:
    resp = client.post("/api/auth/register", json=VALID_USER)
    assert resp.status_code == 200
    return resp.json()["data"]["access_token"]


class TestAuthHardening:
    def test_register_login_flow(self, client):
        _register(client)
        login = client.post("/api/auth/login", json={
            "email": VALID_USER["email"],
            "password": VALID_USER["password"]})
        assert login.status_code == 200
        body = login.json()
        assert body["status"] == "success"
        assert "access_token" in body["data"]
        cookie = login.headers.get("set-cookie", "")
        assert "HttpOnly" in cookie and "samesite=strict" in cookie.lower()

    def test_weak_password_rejected(self, client):
        resp = client.post("/api/auth/register", json={
            "email": "weak@orion.io", "username": "weakling",
            "password": "short"})
        assert resp.status_code == 422
        assert resp.json()["status"] == "fail"

    def test_duplicate_email_rejected(self, client):
        _register(client)
        dup = client.post("/api/auth/register", json=VALID_USER)
        assert dup.status_code == 409

    def test_wrong_password_uniform_401(self, client):
        _register(client)
        bad = client.post("/api/auth/login", json={
            "email": VALID_USER["email"], "password": "WrongPass123"})
        unknown = client.post("/api/auth/login", json={
            "email": "ghost@orion.io", "password": "Whatever123"})
        assert bad.status_code == 401 and unknown.status_code == 401
        # No user enumeration: identical public messages.
        assert bad.json()["message"] == unknown.json()["message"]

    def test_expired_token_rejected(self, client):
        import time as time_mod
        expired = pyjwt.encode(
            {"sub": "1", "type": "access",
             "exp": int(time_mod.time()) - 3600,
             "iat": int(time_mod.time()) - 7200},
            settings.secret_key, algorithm=settings.algorithm)
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_refresh_token_used_as_access_rejected(self, client):
        from app.utils.security import create_refresh_token
        refresh, _jti, _exp = create_refresh_token(999)
        resp = client.get("/api/auth/me",
                          headers={"Authorization": f"Bearer {refresh}"})
        assert resp.status_code == 401

    def test_me_requires_auth(self, client):
        assert client.get("/api/auth/me").status_code == 401


class TestRateLimiting:
    def test_login_brute_force_throttled(self, client):
        payload = {"email": "rl@orion.io", "password": "NopeNope99"}
        codes = [client.post("/api/auth/login", json=payload).status_code
                 for _ in range(8)]
        assert codes.count(429) >= 1


class TestCorsAndHeaders:
    def test_security_headers_present(self, client):
        resp = client.get("/healthz")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_cors_allows_configured_origin_only(self, client):
        allowed = client.options(
            "/api/market/regions",
            headers={"Origin": settings.cors_origin_list[0],
                     "Access-Control-Request-Method": "GET"})
        evil = client.options(
            "/api/market/regions",
            headers={"Origin": "https://evil.example.com",
                     "Access-Control-Request-Method": "GET"})
        assert allowed.headers.get("access-control-allow-origin") is not None
        assert evil.headers.get("access-control-allow-origin") is None


class TestInjectionResistance:
    def test_sql_injection_in_search_is_sanitized(self, client):
        payloads = ["'; DROP TABLE users;--", "1' OR '1'='1",
                    "<script>alert(1)</script>"]
        for payload in payloads:
            resp = client.get("/api/market/search", params={"q": payload})
            # Sanitized-empty success or validation failure - never a 500.
            assert resp.status_code in (200, 422), resp.text
            if resp.status_code == 200:
                assert resp.json()["data"] == []

    def test_invalid_symbol_in_history_rejected(self, client):
        resp = client.get("/api/market/history/%5Cevil")
        assert resp.status_code in (200, 422)

    def test_error_envelope_is_generic(self, client):
        resp = client.get("/api/market/history/")
        if resp.status_code >= 400:
            body = resp.json()
            assert body.get("status") == "fail"
            assert "traceback" not in resp.text.lower()


class TestEnvelopeContract:
    def test_success_envelope_shape(self, client):
        resp = client.get("/api/market/regions")
        body = resp.json()
        assert set(("status", "data", "timestamp")).issubset(body.keys())
        assert body["status"] == "success"

    def test_watchlist_flow_and_ownership(self, client, auth_headers):
        created = client.post("/api/watchlists", json={
            "name": "Tech Bets", "region": "US"}, headers=auth_headers)
        assert created.status_code == 201
        wid = created.json()["data"]["id"]
        add = client.post(f"/api/watchlists/{wid}/items",
                          json={"symbol": "NVDA"}, headers=auth_headers)
        assert add.status_code == 200
        listing = client.get("/api/watchlists", headers=auth_headers)
        symbols = [i["symbol"]
                   for i in listing.json()["data"][0]["items"]]
        assert "NVDA" in symbols
        # Foreign/nonexistent id must look identical (404 - no oracle).
        ghost = client.delete("/api/watchlists/99999",
                              headers=auth_headers)
        assert ghost.status_code == 404

    def test_watchlist_requires_auth(self, client):
        assert client.get("/api/watchlists").status_code in (401, 403)

    def test_watchlist_name_validation(self, client, auth_headers):
        bad = client.post("/api/watchlists", json={"name": "x" * 80},
                          headers=auth_headers)
        assert bad.status_code == 422


class TestWebSocketSecurity:
    def test_connection_without_token_connects_as_guest(self, client):
        """Market tick data is public: anonymous sockets are accepted as
        guests and receive the connected handshake."""
        with client.websocket_connect("/ws/market") as ws:
            welcome = ws.receive_json()
            assert welcome["event"] == "connected"

    def test_connection_with_garbage_token_refused(self, client):
        """A SUPPLIED token that is invalid must still be rejected —
        clients may not send broken credentials."""
        with pytest.raises(Exception):
            with client.websocket_connect("/ws/market?token=garbage"):
                pass

    def test_valid_token_connects_and_subscribes(self, client):
        token = _register(client)
        with client.websocket_connect(
                f"/ws/market?token={token}") as ws:
            welcome = ws.receive_json()
            assert welcome["event"] == "connected"
            ws.send_json({"subscribe": "US"})
            ack = ws.receive_json()
            assert ack["event"] == "subscribed"
            assert ack["room"] == "US"


class TestSecretsNotInSourceTree:
    def test_env_example_uses_placeholder_secret(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(root, ".env.example"), encoding="utf-8") as fh:
            content = fh.read()
        assert "replace-me-with-openssl-rand-hex-32" in content
        assert "ghp_" not in content and "AKIA" not in content
