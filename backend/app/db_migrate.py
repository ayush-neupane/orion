"""Standalone idempotent schema migration: `python -m app.db_migrate`."""
from __future__ import annotations

import sys

from app.database import engine, init_db
from app.utils.logger import configure_logging, get_logger


def main() -> int:
    configure_logging("INFO")
    log = get_logger(__name__)
    try:
        init_db(engine)
        log.info("migration_complete", dialect=engine.dialect.name)
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI must report clearly
        log.error("migration_failed", error=str(exc))
        print(f"Migration failed: {exc}", file=sys.stderr)
        print("Hints: ensure Postgres is reachable and the TimescaleDB "
              "image is used (timescale/timescaledb), and that DATABASE_URL "
              "in .env matches docker-compose credentials.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
