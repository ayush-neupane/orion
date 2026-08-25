"""News aggregator endpoint with sentiment labels per headline.

Freshness policy: headlines are served from a rolling 72-hour window by
default; when that window holds too few items it widens to a HARD maximum
of 7 days. Anything older than 7 days is never served.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query

from app.database import SessionLocal
from app.models import NewsArticle, NewsItemOut, ok
from app.services import universe

router = APIRouter(prefix="/news", tags=["news"])

FRESH_WINDOW = timedelta(days=3)
MAX_WINDOW = timedelta(days=7)
MIN_FRESH_HEADLINES = 5
# Upper bound on rows inspected per request (bounded memory / latency).
_SCAN_LIMIT = 300


def _naive_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; Postgres returns aware. Normalize."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=None)
async def news(region: str = Query(default="GLOBAL"),
               limit: int = Query(default=25, ge=1, le=60)):
    if region not in universe.REGIONS:
        region = "GLOBAL"
    now = datetime.now(timezone.utc)
    fresh_cutoff = _naive_utc(now - FRESH_WINDOW)
    hard_cutoff = _naive_utc(now - MAX_WINDOW)

    with SessionLocal() as db:
        candidates = (db.query(NewsArticle)
                      .order_by(NewsArticle.published_at.desc())
                      .limit(_SCAN_LIMIT).all())
    eligible = [r for r in candidates
                if r.published_at and _naive_utc(r.published_at) >= hard_cutoff]
    in_region = [r for r in eligible
                 if region == "GLOBAL" or r.region == region]
    fresh = [r for r in in_region if _naive_utc(r.published_at) >= fresh_cutoff]
    # Widen to the 7-day hard cap only when the fresh window is too thin.
    chosen = fresh if len(fresh) >= MIN_FRESH_HEADLINES else in_region

    if not chosen:
        # Cold start: bounded synchronous fetch so the panel is never empty.
        from starlette.concurrency import run_in_threadpool
        from app.services.scraper import MAX_NEWS_AGE, fetch_news as scrape_news

        def load():
            now_inner = datetime.now(timezone.utc)
            items = [i for i in scrape_news(region, limit)
                     if isinstance(i.get("published_at"), datetime)
                     and now_inner - i["published_at"] <= MAX_NEWS_AGE]
            with SessionLocal() as db:
                added = 0
                for item in items:
                    if db.query(NewsArticle).filter_by(
                            url=item["url"]).first():
                        continue
                    db.add(NewsArticle(**item))
                    added += 1
                db.commit()
            return items[:limit]
        raw = await run_in_threadpool(load)
        return ok(raw)
    return ok([NewsItemOut.model_validate(r).model_dump(mode="json")
               for r in chosen[:limit]])
