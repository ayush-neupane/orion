"""Market data endpoints: quotes, movers, history, predictions,
Underdog Scanner results, search, and the free Fear & Greed index."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, \
    status

from app.config import get_settings
from app.database import SessionLocal
from app.models import (FearGreedOut, Movers, PredictionOut, Quote,
                        SearchHit, ok)
from app.services import universe
from app.services.predictor import engine as pred_engine
from app.utils.logger import get_logger
from starlette.concurrency import run_in_threadpool

log = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["market"])


def _status_422() -> int:
    """Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY to
    HTTP_422_UNPROCESSABLE_CONTENT; support both versions without
    touching the deprecated attribute (which warns on access)."""
    return getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


# Tiny TTL cache so bursts don't hammer upstream free APIs.
_cache: dict[str, tuple[float, object]] = {}
TTL_SECONDS = 45.0


async def cached(key: str, factory):
    hit = _cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < TTL_SECONDS:
        return hit[1]
    value = await factory()
    _cache[key] = (now, value)
    return value


def _validate_region(region: str) -> str:
    if region not in universe.REGIONS:
        raise HTTPException(_status_422(),
                            f"Unknown region '{region}'")
    return region


def _quotes_sync(region: str) -> list[dict]:
    from app.services.scraper import latest_quote
    symbols = universe.stocks_for(region)[:12]
    out: list[dict] = []
    for sym in symbols:
        try:
            out.append(latest_quote(sym, region))
        except Exception as exc:  # noqa: BLE001 - one bad ticker != 500
            log.warning("quote_failed", symbol=sym, error=str(exc))
    return out


async def _get_quotes(region: str) -> list[Quote]:
    raw = await cached(f"quotes:{region}",
                       lambda: run_in_threadpool(_quotes_sync, region))
    return [Quote.model_validate(q) for q in raw]


@router.get("/regions", response_model=None)
async def regions():
    indices = {r: {"symbol": cfg["index"][0], "name": cfg["index"][1]}
               for r, cfg in universe.UNIVERSE.items()}
    return ok({"regions": universe.REGIONS, "indices": indices})


@router.get("/movers", response_model=None)
async def movers(region: str = Query(default="GLOBAL")):
    region = _validate_region(region)
    quotes = await _get_quotes(region)
    ranked = sorted(quotes, key=lambda q: q.change_percent)
    active = sorted(quotes, key=lambda q: q.volume, reverse=True)
    result = Movers(gainers=list(reversed(ranked[-10:])),
                    losers=ranked[:10],
                    most_active=active[:10])
    return ok(result.model_dump())


@router.get("/history/{symbol}", response_model=None)
async def history(symbol: str, region: str = Query(default="US")):
    region = _validate_region(region)
    from app.models import SYMBOL_RE
    if not SYMBOL_RE.fullmatch(symbol):
        raise HTTPException(_status_422(),
                            "Invalid symbol format")

    def load():
        from app.services.scraper import fetch_history
        bars, simulated = fetch_history(symbol, region)
        return {"bars": bars, "simulated": simulated}

    payload = await run_in_threadpool(load)
    return ok(payload)


@router.get("/predictions", response_model=None)
async def predictions(region: str = Query(default="GLOBAL"),
                      limit: int = Query(default=50, ge=1, le=100)):
    from app.models import Prediction
    region = _validate_region(region)
    cutoff = _freshness_cutoff()
    with SessionLocal() as db:
        query = db.query(Prediction).order_by(
            Prediction.breakout_score.desc())
        rows = (query.filter(Prediction.region == region).all()
                if region != "GLOBAL" else query.all())
        fresh = [r for r in rows if r.computed_at
                 and _as_naive_utc(r.computed_at) >= cutoff]
        if fresh:
            return ok([PredictionOut.model_validate(r).model_dump(mode="json")
                       for r in fresh[:limit]])
    # Cold start / stale: compute inline for immediate usability.
    computed = await run_in_threadpool(_compute_inline, region)
    return ok(computed[:limit])


def _as_naive_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware. Normalize."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _freshness_cutoff() -> datetime:
    from datetime import timedelta
    max_age = max(get_settings().prediction_refresh_minutes * 2, 20)
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=max_age)


def settings_prediction_max_age() -> int:
    return max(get_settings().prediction_refresh_minutes * 2, 20)


def _compute_inline(region: str) -> list[dict]:
    """Bounded cold-start prediction: live history + sentiment per symbol."""
    from app.database import SessionLocal
    from app.models import NewsArticle, Prediction
    from datetime import datetime, timezone

    symbols = universe.stocks_for(region if region != "GLOBAL" else "US")[:10]
    out: list[dict] = []
    with SessionLocal() as db:
        for sym in symbols:
            try:
                from app.services.scraper import fetch_history
                bars, _sim = fetch_history(sym, region)
                if not bars:
                    continue
                recent = db.query(NewsArticle).order_by(
                    NewsArticle.fetched_at.desc()).limit(40).all()
                sentiment = (sum(a.sentiment_score for a in recent) /
                             len(recent)) if recent else 0.0
                result = pred_engine.predict_symbol(bars,
                                                    sentiment=sentiment)
                payload = {"symbol": sym, "region": region, **{
                    k: result[k] for k in
                    ("prob_up", "recommendation", "breakout_score",
                     "pe_ratio", "volume_trend_3d", "sentiment_score")}}
                existing = db.query(Prediction).filter_by(symbol=sym).first()
                if existing is None:
                    existing = Prediction(**payload)
                    db.add(existing)
                else:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                    existing.computed_at = datetime.now(timezone.utc)
                out.append(payload)
            except Exception as exc:  # noqa: BLE001
                log.warning("inline_prediction_failed", symbol=sym,
                            error=str(exc))
        try:
            db.commit()
        except Exception:  # noqa: BLE001 - read path must never 500
            log.exception("inline_prediction_commit_failed")
    return sorted(out, key=lambda p: p["breakout_score"], reverse=True)


@router.get("/underdogs", response_model=None)
async def underdogs(region: str = Query(default="GLOBAL"),
                    limit: int = Query(default=10, ge=1, le=25)):
    from app.models import Prediction
    region = _validate_region(region)
    cutoff = _freshness_cutoff()
    with SessionLocal() as db:
        query = db.query(Prediction).filter(
            Prediction.breakout_score >= 55).order_by(
            Prediction.breakout_score.desc())
        rows = (query.filter(Prediction.region == region).all()
                if region != "GLOBAL" else query.all())
        fresh = [r for r in rows if r.computed_at
                 and _as_naive_utc(r.computed_at) >= cutoff]
        if fresh:
            return ok([PredictionOut.model_validate(r).model_dump(mode="json")
                       for r in fresh[:limit]])
    computed = [p for p in await run_in_threadpool(_compute_inline, region)
                if p["breakout_score"] >= 45]
    return ok(computed[:limit])


@router.get("/search", response_model=None)
async def search(q: str = Query(default="", min_length=1, max_length=40)):
    from app.models import SEARCH_RE
    if not SEARCH_RE.fullmatch(q.strip()):
        return ok([])
    needle = q.strip().lower()
    hits: list[SearchHit] = []
    for region, cfg in universe.UNIVERSE.items():
        idx_sym, idx_name = cfg["index"]
        if needle in idx_name.lower() or needle == idx_sym.lower():
            hits.append(SearchHit(symbol=idx_sym, name=f"{idx_name} (Index)",
                                  region=region))
        for stock in cfg["stocks"]:
            if needle in stock.lower():
                hits.append(SearchHit(symbol=stock, name=stock,
                                      region=region))
    return ok([h.model_dump() for h in hits[:12]])


@router.get("/fear-greed", response_model=None)
async def fear_greed():
    async def compute():
        def load():
            from app.services.scraper import fetch_history
            bars, _sim = fetch_history("^GSPC", "US")
            return pred_engine.compute_fear_greed(bars or [])
        return await run_in_threadpool(load)

    result = await cached("fear_greed", compute)
    return ok(FearGreedOut(**result).model_dump())


@router.get("/overview", response_model=None)
async def overview(region: str = Query(default="GLOBAL")):
    region = _validate_region(region)
    quotes = await _get_quotes(region)
    movers_payload = await movers(region=region)
    fg = await fear_greed_inner()
    index_sym, index_name = universe.index_for(
        region if region != "GLOBAL" else "US")
    return ok({
        "index": {"symbol": index_sym, "name": index_name},
        "quotes": [q.model_dump() for q in quotes],
        "movers": movers_payload,
        "fear_greed": fg,
    })


async def fear_greed_inner() -> dict | None:
    result = await cached("fear_greed", lambda: run_in_threadpool(
        lambda: pred_engine.compute_fear_greed(
            _index_bars_sync())))
    return FearGreedOut(**result).model_dump()


def _index_bars_sync() -> list[dict]:
    try:
        from app.services.scraper import fetch_history
        bars, _sim = fetch_history("^GSPC", "US")
        return bars or []
    except Exception:  # noqa: BLE001
        return []
