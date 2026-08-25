"""Structured JSON logging via structlog.

Production: JSON lines to file (never leak stack traces to clients).
Development: pretty console output.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

import structlog

_CONFIGURED = False


def configure_logging(level: str = "INFO", log_file: str = "logs/orion.log",
                      production: bool = False) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    fmt = logging.Formatter("%(message)s")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    shared = [structlog.processors.TimeStamper(fmt="iso"),
              structlog.processors.add_log_level,
              structlog.processors.StackInfoRenderer(),
              structlog.processors.format_exc_info]
    renderer = (structlog.processors.JSONRenderer()
                if production else structlog.dev.ConsoleRenderer())
    structlog.configure(
        processors=shared + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    # Quiet noisy third-party loggers; their records still reach the JSON file.
    for name in ("uvicorn.access", "celery.app.trace"):
        logging.getLogger(name).handlers.clear()
    _CONFIGURED = True


def get_logger(name: str = "orion") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
