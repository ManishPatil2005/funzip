"""Cache port. Closed bars are immutable so they cache by key forever (until TTL);
the forming bar is never cached. Redis adapter is a thin skeleton behind the same protocol."""
from __future__ import annotations

import json
import time
from typing import Any, Protocol


class Cache(Protocol):
    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl: float) -> None: ...


class MemoryCache:
    def __init__(self, max_items: int = 512) -> None:
        self._d: dict[str, tuple[float, Any]] = {}
        self._max = max_items

    def get(self, key: str) -> Any | None:
        hit = self._d.get(key)
        if hit is None:
            return None
        if hit[0] < time.monotonic():
            del self._d[key]
            return None
        return hit[1]

    def set(self, key: str, value: Any, ttl: float) -> None:
        if len(self._d) >= self._max:
            self._d.pop(next(iter(self._d)))  # FIFO eviction keeps memory bounded
        self._d[key] = (time.monotonic() + ttl, value)


class RedisCache:  # pragma: no cover - needs a server
    def __init__(self, url: str) -> None:
        import redis  # lazy: optional dependency

        self._r = redis.Redis.from_url(url)

    def get(self, key: str) -> Any | None:
        raw = self._r.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl: float) -> None:
        self._r.set(key, json.dumps(value), ex=max(1, int(ttl)))
