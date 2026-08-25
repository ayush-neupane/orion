"""Database engine, session factory and idempotent schema bootstrap.

Postgres/TimescaleDB in deployment; SQLite-compatible for the test suite
(hypertable DDL is applied only on PostgreSQL).
"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings
from app.utils.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"check_same_thread": False}
    if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False,
                            expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(target_engine=engine) -> None:
    """Create tables + TimescaleDB hypertable. Safe to run repeatedly."""
    # Imported for model registration side effects.
    from app import models  # noqa: F401

    is_pg = target_engine.dialect.name == "postgresql"
    if is_pg:
        with target_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
            conn.commit()
    Base.metadata.create_all(bind=target_engine)
    if is_pg:
        try:
            with target_engine.begin() as conn:
                conn.execute(text(
                    "SELECT create_hypertable('price_bars', 'ts', "
                    "if_not_exists => TRUE, migrate_data => TRUE)"))
            log.info("timescale_hypertable_ready")
        except Exception as exc:  # noqa: BLE001 - plain PG still works
            log.warning("hypertable_creation_skipped", error=str(exc))
    log.info("database_schema_ready", dialect=target_engine.dialect.name)
