"""Authentication, rate limiting, request-size limits and security headers."""
from __future__ import annotations

import hmac
import logging
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.config import Settings, get_settings

log = logging.getLogger("scanner.security")


# --------------------------------------------------------------------------- auth
def require_api_key(request: Request, settings: Settings = Depends(get_settings)) -> str:
    """Validate the X-API-Key header using constant-time comparison."""
    if not settings.api_keys:
        if settings.is_production:  # pragma: no cover - blocked at startup too
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication not configured")
        return "dev"  # development only: auth disabled when no keys configured

    supplied = request.headers.get("x-api-key", "")
    matched = False
    for key in settings.api_keys:  # no early exit: avoid timing differences
        if hmac.compare_digest(supplied.encode(), key.encode()):
            matched = True
    if not matched:
        log.warning("auth_failed ip=%s path=%s", client_ip(request), request.url.path)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing API key")
    return supplied[:6] + "..."


def client_ip(request: Request) -> str:
    # X-Forwarded-For is honoured only when SCANNER_TRUST_PROXY=true, i.e. when the
    # app is reachable solely through our reverse proxy (which overwrites the header).
    # Otherwise any client could spoof it to dodge the rate limiter.
    if get_settings().trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ------------------------------------------------------------------ rate limiting
class SlidingWindowLimiter:
    """Thread-safe in-memory sliding window limiter (per process)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False, max(1, int(window - (now - hits[0])))
            hits.append(now)
            if len(self._hits) > 10_000:  # bound memory
                self._evict(now, window)
            return True, 0

    def _evict(self, now: float, window: float) -> None:
        for k in [k for k, v in self._hits.items() if not v or now - v[-1] > window]:
            self._hits.pop(k, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in ("/healthz", "/readyz") or path.startswith("/static"):
            return await call_next(request)
        ip = client_ip(request)
        limit = self.settings.rate_limit_per_minute
        bucket = f"g:{ip}"
        if path == "/api/scan":
            limit = self.settings.scan_rate_limit_per_minute
            bucket = f"s:{ip}"
        ok, retry = limiter.allow(bucket, limit)
        if not ok:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        return await call_next(request)


# ------------------------------------------------------------------ request size
class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_bytes: int):
        super().__init__(app)
        self.max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next):
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > self.max_bytes:
            return JSONResponse({"detail": "Request body too large"}, status_code=413)
        if request.method in ("POST", "PUT", "PATCH") and not declared:
            body = await request.body()
            if len(body) > self.max_bytes:
                return JSONResponse({"detail": "Request body too large"}, status_code=413)
        return await call_next(request)


# ---------------------------------------------------------------- security headers
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, hsts: bool = False):
        super().__init__(app)
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        h = response.headers
        h["Content-Security-Policy"] = CSP
        h["X-Content-Type-Options"] = "nosniff"
        h["X-Frame-Options"] = "DENY"
        h["Referrer-Policy"] = "no-referrer"
        h["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        h["Cross-Origin-Opener-Policy"] = "same-origin"
        h["Cross-Origin-Resource-Policy"] = "same-origin"
        if request.url.path.startswith("/api"):
            h["Cache-Control"] = "no-store"
        if self.hsts:
            h["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        if "server" in h:
            del h["server"]
        return response
