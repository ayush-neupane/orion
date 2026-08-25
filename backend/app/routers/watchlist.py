"""Per-user watchlist CRUD with strict ownership enforcement."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import SessionLocal
from app.models import (Watchlist, WatchlistCreate,
                        WatchlistItem, WatchlistItemCreate, WatchlistOut,
                        ok)
from app.utils.logger import get_logger
from app.utils.security import get_current_user

log = get_logger(__name__)
router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=None)
def list_watchlists(user=Depends(get_current_user)):
    with SessionLocal() as db:
        rows = db.query(Watchlist).filter_by(user_id=user.id).all()
        return ok([WatchlistOut.model_validate(w).model_dump(mode="json")
                   for w in rows])


@router.post("", status_code=201, response_model=None)
def create_watchlist(payload: WatchlistCreate, user=Depends(get_current_user)):
    with SessionLocal() as db:
        existing = db.query(Watchlist).filter_by(
            user_id=user.id, name=payload.name).first()
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "Watchlist name already exists")
        watchlist = Watchlist(user_id=user.id, name=payload.name,
                              region=payload.region)
        db.add(watchlist)
        db.commit()
        db.refresh(watchlist)
        return ok(WatchlistOut.model_validate(watchlist).model_dump(
            mode="json"))


def _owned_watchlist(db, watchlist_id: int, user_id: int) -> Watchlist:
    watchlist = db.query(Watchlist).filter_by(id=watchlist_id).first()
    if watchlist is None or watchlist.user_id != user_id:
        # 404 for both missing AND foreign-owned: no existence oracle.
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            "Watchlist not found")
    return watchlist


@router.delete("/{watchlist_id}", response_model=None)
def delete_watchlist(watchlist_id: int, user=Depends(get_current_user)):
    with SessionLocal() as db:
        watchlist = _owned_watchlist(db, watchlist_id, user.id)
        db.delete(watchlist)
        db.commit()
    return ok({"deleted": watchlist_id})


@router.post("/{watchlist_id}/items", response_model=None)
def add_symbol(watchlist_id: int, payload: WatchlistItemCreate,
               user=Depends(get_current_user)):
    with SessionLocal() as db:
        watchlist = _owned_watchlist(db, watchlist_id, user.id)
        if db.query(WatchlistItem).filter_by(
                watchlist_id=watchlist.id,
                symbol=payload.symbol).first():
            return ok(WatchlistOut.model_validate(watchlist).model_dump(
                mode="json"))
        db.add(WatchlistItem(watchlist_id=watchlist.id,
                             symbol=payload.symbol))
        db.commit()
        db.refresh(watchlist)
        return ok(WatchlistOut.model_validate(watchlist).model_dump(
            mode="json"))


@router.delete("/{watchlist_id}/items/{symbol}", response_model=None)
def remove_symbol(watchlist_id: int, symbol: str,
                  user=Depends(get_current_user)):
    with SessionLocal() as db:
        watchlist = _owned_watchlist(db, watchlist_id, user.id)
        item = db.query(WatchlistItem).filter_by(
            watchlist_id=watchlist.id, symbol=symbol.upper()).first()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Symbol not found")
        db.delete(item)
        db.commit()
        db.refresh(watchlist)
        return ok(WatchlistOut.model_validate(watchlist).model_dump(
            mode="json"))
