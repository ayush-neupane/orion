"""HTTP hardening middleware and rate limiting.

- SecurityHeadersMiddleware: CSP, HSTS (prod), anti-clickjacking, MIME
  sniffing protection, referrer/permissions policy on every response.
- RequestIDMiddleware: correlates log lines per request.
- slowapi limiter: per-IP request throttling backed by memory or Redis.
"""
from __future__ import annotations

import time
import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import get_settings
from app.utils.logger import get_logger

settings = get_settings()
log = get_logger(__name__)

limiter = Limiter(key_func=get_remote_address,
                  storage_uri=settings.ratelimit_storage_uri)

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "font-src 'self'; connect-src 'self' ws: wss:; frame-ancestors 'none'; "
       "base-uri 'self'; form-action 'self'")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request,
                       call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy",
                                    "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy",
                                    "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains; preload")
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log.info("http_request", method=request.method,
                 path=request.url.path, status=response.status_code,
                 duration_ms=elapsed_ms, request_id=request_id)
        return response
