"""ORION backend entry point.

- Lifespan-managed startup/shutdown (DB bootstrap, WS broadcaster, clean
  resource disposal on SIGTERM).
- Uniform response envelope: {status, data, message, timestamp}.
- Global exception handlers: clients only ever see generic messages;
  detailed stack traces go to the JSON log file via structlog.
"""
from __future__ import annotations

import asyncio
import contextlib
import signal as signal_module
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.database import engine, init_db
from app.middleware.security import (RequestIDMiddleware,
                                     SecurityHeadersMiddleware, limiter)
from app.models import fail
from app.routers import auth, market, news, watchlist
from app.routers.ws import router as ws_router
from app.utils.logger import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level, settings.log_file,
                  production=settings.is_production)
log = get_logger(__name__)

_broadcaster_task: asyncio.Task | None = None


async def _tick_broadcaster() -> None:
    """Pushes lightweight synthetic ticks derived from the latest quotes so
    connected dashboards stay live between Celery ingestion cycles."""
    from starlette.concurrency import run_in_threadpool
    from app.websocket_manager import manager
    from app.services import universe
    from app.services.scraper import latest_quote

    counter = 0
    while True:
        try:
            for room in list(manager.active_rooms):
                region = room if room in universe.REGIONS else "US"
                symbols = universe.stocks_for(region)[:8]
                if not symbols:
                    continue
                sym = symbols[counter % len(symbols)]
                quote = await run_in_threadpool(latest_quote, sym, region)
                quote["price"] = round(
                    quote["price"] * (1 + ((counter % 7) - 3) * 0.0004), 4)
                await manager.broadcast(room, {"event": "tick", **quote})
            counter += 1
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - broadcaster must survive
            log.warning("broadcaster_error", error=str(exc))
        await asyncio.sleep(3)


async def _shutdown() -> None:
    global _broadcaster_task
    log.info("orion_shutting_down")
    if _broadcaster_task is not None:
        _broadcaster_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _broadcaster_task
        _broadcaster_task = None
    with contextlib.suppress(Exception):
        engine.dispose()
    log.info("resources_released")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _broadcaster_task
    log.info("orion_starting", environment=settings.environment)
    try:
        init_db(engine)
    except Exception as exc:  # noqa: BLE001 - DB may still be warming up
        log.error("db_bootstrap_failed_run_make_migrate", error=str(exc))
    loop = asyncio.get_running_loop()
    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal_module, sig_name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(
                    sig, lambda s=sig_name: (
                        log.info("shutdown_signal_received", signal=s),
                        asyncio.create_task(_shutdown())))
            except NotImplementedError:  # pragma: no cover - Windows dev
                pass
    _broadcaster_task = asyncio.create_task(_tick_broadcaster())
    yield
    await _shutdown()


def _rate_limit_handler(request: Request, exc) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        content=fail(
                            "Too many requests - please slow down"
                        ).model_dump())


app = FastAPI(title="ORION Market Intelligence API",
              version="1.0.0",
              docs_url=None if settings.is_production else "/docs",
              lifespan=lifespan)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CORSMiddleware,
                   allow_origins=settings.cors_origin_list,
                   allow_credentials=True,
                   allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Authorization", "Content-Type",
                                  "X-Request-ID"])


# ------------------------- global exception handlers -------------------------

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request,
                                 exc: StarletteHTTPException):
    """Uniform envelope for every deliberate HTTP error (401/403/404/409…),
    covering both Starlette router errors and FastAPI HTTPExceptions.
    Detail messages are developer-authored strings, never raw tracebacks."""
    headers = getattr(exc, "headers", None)
    response = JSONResponse(status_code=exc.status_code,
                            content=fail(str(exc.detail)).model_dump())
    if headers:
        for key, value in headers.items():
            response.headers[key] = value
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    log.warning("validation_error", path=request.url.path,
                error_count=len(exc.errors()))
    return JSONResponse(status_code=422, content=fail(
        "Invalid request payload").model_dump())


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    log.error("database_error", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content=fail().model_dump())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.exception("unhandled_error", path=request.url.path)
    return JSONResponse(status_code=500, content=fail().model_dump())


# --------------------------------- routes -----------------------------------

@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


app.include_router(auth.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(watchlist.router, prefix="/api")
app.include_router(ws_router)
