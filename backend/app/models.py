"""ORM models and Pydantic v2 request/response schemas.

All persistence flows through the SQLAlchemy ORM (parameterized queries);
all inbound payloads are validated by Pydantic with strict regex/length
constraints. Every API response is wrapped in the Envelope schema.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import (BigInteger, Boolean, DateTime, Float, ForeignKey,
                        Index, Integer, String, Text, UniqueConstraint,
                        func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# --------------------------------------------------------------------------
# SQLAlchemy ORM models
# --------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)

    watchlists: Mapped[list["Watchlist"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan")


class RefreshTokenRecord(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    token_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class Watchlist(Base):
    __tablename__ = "watchlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(8), default="GLOBAL")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow)

    owner: Mapped[User] = relationship(back_populates="watchlists")
    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("watchlist_id", "symbol",
                                       name="uq_watchlist_symbol"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    watchlist_id: Mapped[int] = mapped_column(
        ForeignKey("watchlists.id"), index=True)
    symbol: Mapped[str] = mapped_column(String(20))

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class PriceBar(Base):
    """Time-series OHLCV row. Composite PK (symbol, ts) makes ingestion
    idempotent and satisfies TimescaleDB hypertable requirements."""
    __tablename__ = "price_bars"
    __table_args__ = (Index("ix_price_bars_ts", "ts"),)

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                         primary_key=True)
    region: Mapped[str] = mapped_column(String(8), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[int] = mapped_column(BigInteger, default=0)


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(120))
    region: Mapped[str] = mapped_column(String(8), default="GLOBAL",
                                        index=True)
    sentiment_label: Mapped[str] = mapped_column(String(12), default="NEUTRAL")
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                   default=utcnow)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow)


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (Index("ix_predictions_region", "region"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    region: Mapped[str] = mapped_column(String(8))
    prob_up: Mapped[float] = mapped_column(Float)
    recommendation: Mapped[str] = mapped_column(String(8))
    breakout_score: Mapped[int] = mapped_column(Integer)
    pe_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_trend_3d: Mapped[float] = mapped_column(Float, default=0.0)
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())

# --------------------------------------------------------------------------
# Pydantic v2 schemas (request validation + response contracts)
# --------------------------------------------------------------------------


T = TypeVar("T")

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,32}$")
SYMBOL_RE = re.compile(r"^[A-Za-z0-9.^=\-]{1,20}$")
WATCHLIST_NAME_RE = re.compile(r"^[\w\s\-']{1,64}$")
SEARCH_RE = re.compile(r"^[A-Za-z0-9.\s\-]{1,40}$")


class Envelope(BaseModel, Generic[T]):
    status: Literal["success", "fail"]
    data: T | None = None
    message: str | None = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


def ok(data) -> Envelope:
    return Envelope(status="success", data=data)


def fail(message: str = "An internal error occurred") -> Envelope:
    return Envelope(status="fail", message=message)


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def _username(cls, v: str) -> str:
        if not USERNAME_RE.fullmatch(v):
            raise ValueError(
                "username must be 3-32 chars: letters, digits, underscore")
        return v

    @field_validator("password")
    @classmethod
    def _password(cls, v: str) -> str:
        if not 10 <= len(v) <= 128:
            raise ValueError("password must be between 10 and 128 characters")
        if not re.search(r"[A-Z]", v) or not re.search(r"\d", v):
            raise ValueError(
                "password needs at least one uppercase letter and one digit")
        return v


class UserOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    email: str
    username: str
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class TokenPair(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class WatchlistCreate(BaseModel):
    name: str
    region: str = "GLOBAL"

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not WATCHLIST_NAME_RE.fullmatch(v.strip()):
            raise ValueError("watchlist name must be 1-64 safe characters")
        return v.strip()


class WatchlistItemCreate(BaseModel):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, v: str) -> str:
        if not SYMBOL_RE.fullmatch(v.strip().upper()):
            raise ValueError("invalid ticker symbol format")
        return v.strip().upper()


class WatchlistItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str


class WatchlistOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    region: str
    items: list[WatchlistItemOut] = []


class Quote(BaseModel):
    symbol: str
    name: str = ""
    price: float
    change: float = 0.0
    change_percent: float = 0.0
    volume: int = 0
    simulated: bool = False


class Movers(BaseModel):
    gainers: list[Quote] = []
    losers: list[Quote] = []
    most_active: list[Quote] = []


class HistoryPoint(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class PredictionOut(BaseModel):
    model_config = {"from_attributes": True}

    symbol: str
    region: str
    prob_up: float
    recommendation: str
    breakout_score: int
    pe_ratio: float | None = None
    volume_trend_3d: float = 0.0
    sentiment_score: float = 0.0
    computed_at: datetime | None = None


class NewsItemOut(BaseModel):
    model_config = {"from_attributes": True}

    url: str
    title: str
    source: str
    region: str
    sentiment_label: str
    sentiment_score: float
    published_at: datetime


class SearchHit(BaseModel):
    symbol: str
    name: str
    region: str


class FearGreedOut(BaseModel):
    score: int
    label: str
    components: dict[str, float] = {}
