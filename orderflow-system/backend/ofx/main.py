"""FastAPI application factory."""
from __future__ import annotations

import asyncio
import hmac
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ofx.api.hub import Hub
from ofx.api.service import TF, BadRequest, Service
from ofx.ingest import run_ingest
from ofx.orderflow.market_profile import CRYPTO_UTC_DAY, MCX_COMMODITY, NSE_EQUITY
from ofx.providers.base import MarketDataProvider
from ofx.providers.synthetic import SyntheticProvider

Start = Annotated[datetime, Query()]
Tick = Annotated[float, Query(gt=0)]
SESSIONS = {"NSE": NSE_EQUITY, "MCX": MCX_COMMODITY, "CRYPTO": CRYPTO_UTC_DAY}


def create_app(provider: MarketDataProvider | None = None, api_key: str | None = None, rate_per_min: int | None = None) -> FastAPI:
    key = api_key if api_key is not None else os.environ.get("OFX_API_KEY", "")
    origins = [o for o in os.environ.get("OFX_CORS_ORIGINS", "").split(",") if o]
    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        task = None
        iid = os.environ.get("OFX_LIVE_IID")
        if iid:  # opt-in live ingest: OFX_LIVE_IID=SYN:TEST OFX_LIVE_TICK=0.5 OFX_LIVE_TF=1m
            tf = timedelta(seconds=TF[os.environ.get("OFX_LIVE_TF", "1m")])
            task = asyncio.create_task(run_ingest(svc.p, iid, float(os.environ.get("OFX_LIVE_TICK", "0.5")), tf, hub))
        try:
            yield
        finally:
            if task:
                task.cancel()

    app = FastAPI(title="Order Flow API", version="0.1.0", docs_url="/docs", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=["x-api-key"])
    svc = Service(provider or SyntheticProvider())
    limit = rate_per_min if rate_per_min is not None else int(os.environ.get("OFX_RATE_PER_MIN", "120"))
    trust_proxy = os.environ.get("OFX_TRUST_PROXY") == "1"
    buckets: dict[str, tuple[float, float]] = {}  # ip -> (tokens, last_ts)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):  # type: ignore[no-untyped-def]
        if limit > 0 and request.url.path != "/health":
            ip = request.client.host if request.client else "?"
            if trust_proxy and request.headers.get("x-forwarded-for"):
                ip = request.headers["x-forwarded-for"].split(",")[0].strip()
            now = time.monotonic()
            tokens, last = buckets.get(ip, (float(limit), now))
            tokens = min(float(limit), tokens + (now - last) * limit / 60.0)
            if tokens < 1:
                return JSONResponse({"error": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "1"})
            if len(buckets) > 10_000:
                buckets.clear()  # bound memory; worst case a brief reset of limits
            buckets[ip] = (tokens - 1, now)
        return await call_next(request)
    hub = Hub()

    def auth(x_api_key: Annotated[str | None, Header()] = None) -> None:
        # Constant-time compare; when no key is configured the API is open (dev only).
        if key and not hmac.compare_digest(x_api_key or "", key):
            raise HTTPException(401, "invalid api key")

    Auth = Depends(auth)

    @app.exception_handler(BadRequest)
    async def _bad(_, exc: BadRequest):  # type: ignore[no-untyped-def]
        return JSONResponse({"error": str(exc)}, status_code=400)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/capabilities", dependencies=[Auth])
    async def caps() -> dict:
        c = svc.p.capabilities
        return {**c.__dict__, "trade_quality": c.trade_quality.value}

    @app.get("/api/v1/footprint", dependencies=[Auth])
    async def footprint(iid: str, tick: Tick, start: Start, end: Start, tf: str = "5m",
                        ratio: Annotated[float, Query(ge=1.1, le=20)] = 3.0) -> dict:
        return await svc.footprint(iid, tick, start, end, tf, ratio)

    @app.get("/api/v1/volume-profile", dependencies=[Auth])
    async def volume_profile(iid: str, tick: Tick, start: Start, end: Start) -> dict:
        return await svc.volume_profile(iid, tick, start, end)

    @app.get("/api/v1/market-profile", dependencies=[Auth])
    async def market_profile(iid: str, tick: Tick, start: Start, end: Start, session: str = "NSE", period: Annotated[int, Query(ge=5, le=60)] = 30) -> dict:
        if session not in SESSIONS:
            raise BadRequest(f"session must be one of {sorted(SESSIONS)}")
        return await svc.market_profile(iid, tick, start, end, SESSIONS[session], period)

    @app.get("/api/v1/observations", dependencies=[Auth])
    async def observations(iid: str, tick: Tick, start: Start, end: Start, tf: str = "5m") -> dict:
        return await svc.observations(iid, tick, start, end, tf)

    @app.get("/api/v1/heatmap", dependencies=[Auth])
    async def heatmap(iid: str, tick: Tick, start: Start, end: Start, dt: Annotated[float, Query(gt=0, le=3600)] = 5.0,
                      scale: str = "log", mode: str = "max") -> dict:
        return await svc.heatmap(iid, tick, start, end, dt, scale, mode)

    @app.websocket("/ws/v1/stream")
    async def stream(ws: WebSocket, topic: str, x_api_key: str = "") -> None:
        if key and not hmac.compare_digest(x_api_key, key):
            await ws.close(code=4401)
            return
        await ws.accept()
        client = hub.subscribe(topic)
        try:
            while True:
                await ws.send_json(await client.queue.get())
        except WebSocketDisconnect:
            pass
        finally:
            hub.unsubscribe(topic, client)

    app.state.hub = hub
    return app


app = create_app()
