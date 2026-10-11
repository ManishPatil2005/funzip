"""Application settings, read from environment variables.

Production mode refuses to start without a strong API key, so the service
can never be deployed accidentally in an unauthenticated state.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _csv(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    env: str = "development"
    api_keys: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    cors_origins: tuple[str, ...] = ()
    database_path: str = "data/scanner.db"
    data_provider: str = "yfinance"  # yfinance | synthetic
    cache_ttl_seconds: int = 300
    rate_limit_per_minute: int = 60
    scan_rate_limit_per_minute: int = 10
    max_body_bytes: int = 64 * 1024
    max_scan_symbols: int = 60
    scan_workers: int = 8
    log_level: str = "INFO"
    hsts: bool = False
    trust_proxy: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    def validate(self) -> None:
        if self.is_production:
            if not self.api_keys:
                raise RuntimeError("SCANNER_API_KEYS must be set when SCANNER_ENV=production")
            if any(len(k) < 32 for k in self.api_keys):
                raise RuntimeError("Every API key must be at least 32 characters in production")
            if "*" in self.allowed_hosts:
                raise RuntimeError("SCANNER_ALLOWED_HOSTS must not contain '*' in production")
            if self.data_provider == "synthetic":
                raise RuntimeError("The synthetic data provider is not permitted in production")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings(
        env=os.getenv("SCANNER_ENV", "development").lower(),
        api_keys=tuple(_csv("SCANNER_API_KEYS")),
        allowed_hosts=tuple(_csv("SCANNER_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")),
        cors_origins=tuple(_csv("SCANNER_CORS_ORIGINS")),
        database_path=os.getenv("SCANNER_DATABASE_PATH", "data/scanner.db"),
        data_provider=os.getenv("SCANNER_DATA_PROVIDER", "yfinance").lower(),
        cache_ttl_seconds=_int("SCANNER_CACHE_TTL", 300),
        rate_limit_per_minute=_int("SCANNER_RATE_LIMIT", 60),
        scan_rate_limit_per_minute=_int("SCANNER_SCAN_RATE_LIMIT", 10),
        max_scan_symbols=_int("SCANNER_MAX_SCAN_SYMBOLS", 60),
        scan_workers=_int("SCANNER_SCAN_WORKERS", 8),
        log_level=os.getenv("SCANNER_LOG_LEVEL", "INFO").upper(),
        hsts=os.getenv("SCANNER_HSTS", "false").lower() == "true",
        trust_proxy=os.getenv("SCANNER_TRUST_PROXY", "false").lower() == "true",
    )
    settings.validate()
    return settings
