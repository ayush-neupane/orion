"""Central, typed application settings. No secrets are ever hardcoded:
everything is read from environment variables / a local .env file.

The .env lookup checks BOTH the current directory and the repository root,
so the backend boots correctly whether launched from `backend/` or the
repo root (a common native-run mistake that previously made the API fall
back to the Docker-only `postgres` hostname and 500 on every DB endpoint).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8",
        extra="ignore")

    environment: str = "development"
    secret_key: str = "insecure-dev-only-secret-change-me-in-.env"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:8080,http://localhost:5173"

    # Native runs default to zero-dependency SQLite; docker-compose always
    # injects the PostgreSQL URL explicitly, so deployment is unchanged.
    database_url: str = "sqlite:///./orion.db"
    redis_url: str = "redis://localhost:6379/0"
    ratelimit_storage_uri: str = "memory://"

    alpha_vantage_key: str = ""
    news_api_key: str = ""
    proxy_url: str = ""

    ingest_interval_seconds: int = 60
    news_refresh_minutes: int = 30
    prediction_refresh_minutes: int = 10
    max_ws_message_bytes: int = 1_048_576

    log_level: str = "INFO"
    log_file: str = "logs/orion.log"
    cookie_secure: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
