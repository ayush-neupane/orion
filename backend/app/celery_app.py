"""Celery application: scheduled, IDEMPOTENT ingestion + prediction jobs.

Idempotency: price bars use composite PK (symbol, ts) with conflict-ignore;
news dedupes on unique URL; predictions upsert by unique symbol.
Reliability: exponential-backoff retries, max 3, then critical log.
"""
from __future__ import annotations

from datetime import datetime, timezone

from celery import Celery
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.config import get_settings
from app.models import NewsArticle, PriceBar, Prediction
from app.services import scraper, universe
from app.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

celery = Celery("orion", broker=settings.redis_url,
                backend=settings.redis_url)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)


def _upsert_bars(db, rows: list[dict], symbol: str, region: str) -> int:
    """Insert-or-skip. Idempotent on both Postgres and SQLite."""
    inserted = 0
    is_pg = getattr(db.bind, "dialect", None) and \
        db.bind.dialect.name == "postgresql"
    for row in rows:
        record = {
            "symbol": symbol,
            "ts": datetime.strptime(row["time"], "%Y-%m-%d").replace(
                tzinfo=timezone.utc),
            "region": region,
            "open": row["open"], "high": row["high"],
            "low": row["low"], "close": row["close"],
            "volume": int(row.get("volume", 0)),
        }
        if is_pg:
            stmt = pg_insert(PriceBar).values(**record)
            db.execute(stmt.on_conflict_do_nothing())
        else:
            exists = db.query(PriceBar).filter_by(
                symbol=record["symbol"], ts=record["ts"]).first()
            if exists:
                continue
            db.add(PriceBar(**record))
        inserted += 1
    return inserted


def _upsert_news(db, items: list[dict]) -> int:
    added = 0
    for item in items:
        if db.query(NewsArticle).filter_by(url=item["url"]).first():
            continue
        db.add(NewsArticle(**item))
        added += 1
    return added


def _retrying(bind_self, exc: Exception, task_name: str) -> None:
    retries = bind_self.request.retries
    if retries >= 3:
        log.critical("task_permanent_failure", task=task_name,
                     error=str(exc), retries=retries)
        return
    bind_self.retry(exc=exc, countdown=min(2 ** (retries + 1) * 10, 120))


@celery.task(bind=True, name="orion.ingest_prices",
             autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_prices(self) -> dict:
    from app.database import SessionLocal
    total = 0
    try:
        with SessionLocal() as db:
            for region in universe.REGIONS[1:]:
                index_symbol = universe.UNIVERSE.get(region, {}).get(
                    "index", (None,))[0]
                max_symbols = scraper.MAX_SYMBOLS_PER_REGION
                targets = ([index_symbol] if index_symbol else []) + \
                    universe.stocks_for(region)[:max_symbols]
                for sym in targets:
                    bars, _simulated = scraper.fetch_history(sym, region)
                    if bars:
                        total += _upsert_bars(db, bars[-90:], sym, region)
            db.commit()
        log.info("ingest_prices_done", rows_inserted=total)
        return {"rows_inserted": total}
    except (SQLAlchemyError, IntegrityError) as exc:
        _retrying(self, exc, "ingest_prices")
        return {"error": str(exc)}


@celery.task(bind=True, name="orion.ingest_news",
             autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def ingest_news(self) -> dict:
    from app.database import SessionLocal
    total = 0
    try:
        with SessionLocal() as db:
            for region in universe.REGIONS:
                total += _upsert_news(db, scraper.fetch_news(region))
            db.commit()
        log.info("ingest_news_done", articles_added=total)
        return {"articles_added": total}
    except SQLAlchemyError as exc:
        _retrying(self, exc, "ingest_news")
        return {"error": str(exc)}


@celery.task(bind=True, name="orion.compute_predictions",
             autoretry_for=(Exception,), retry_backoff=True, max_retries=3)
def compute_predictions(self) -> dict:
    from app.database import SessionLocal
    from app.services.predictor import engine as pred_engine

    computed = 0
    try:
        with SessionLocal() as db:
            for region in universe.REGIONS[1:]:
                for sym in universe.stocks_for(region):
                    rows = db.query(PriceBar).filter_by(symbol=sym).order_by(
                        PriceBar.ts).all()
                    if len(rows) < 12:
                        continue
                    bars = [{"time": r.ts.strftime("%Y-%m-%d"), "open": r.open,
                             "high": r.high, "low": r.low, "close": r.close,
                             "volume": r.volume} for r in rows]
                    result = pred_engine.predict_symbol(bars)
                    payload = {"symbol": sym, "region": region, **{
                        k: result[k] for k in
                        ("prob_up", "recommendation", "breakout_score",
                         "pe_ratio", "volume_trend_3d", "sentiment_score")}}
                    existing = db.query(Prediction).filter_by(
                        symbol=sym).first()
                    if existing:
                        for key, value in payload.items():
                            setattr(existing, key, value)
                        existing.computed_at = datetime.now(timezone.utc)
                    else:
                        db.add(Prediction(**payload))
                    computed += 1
            db.commit()
        log.info("predictions_computed", count=computed)
        return {"computed": computed}
    except SQLAlchemyError as exc:
        _retrying(self, exc, "compute_predictions")
        return {"error": str(exc)}


celery.conf.beat_schedule = {
    "ingest-prices": {
        "task": "orion.ingest_prices",
        "schedule": max(float(settings.ingest_interval_seconds), 60.0),
    },
    "ingest-news": {
        "task": "orion.ingest_news",
        "schedule": settings.news_refresh_minutes * 60.0,
    },
    "compute-predictions": {
        "task": "orion.compute_predictions",
        "schedule": settings.prediction_refresh_minutes * 60.0,
    },
}
