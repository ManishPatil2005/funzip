"""Delta Exchange adapter: PUBLIC market data (products, candles, trades) + websocket parsing.

Market data endpoints are public, so this adapter needs NO API key for data. Keys are only
needed for private endpoints, which this project does not use (no orders, no balances).
`sign` / `signed_headers` remain as a tested helper for a future private call.

UNVERIFIED (sandbox cannot reach the exchange; confirm with scripts/smoke_live.py on your machine):
  * Path names and field names below follow the public docs as I know them.
  * Trade payloads carry `buyer_role` / `seller_role` ("taker"/"maker"). If so, the aggressor is
    exchange-reported (EXACT). Until you confirm, pass aggressor_verified=False (default): sides are
    still parsed but the feed is labelled ESTIMATED.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

import httpx

from ofx.domain import AggressorSide, Candle, DepthLevel, DepthSnapshot, Instrument, Quote, Trade
from ofx.providers.base import Capabilities, ProviderUnsupported

INDIA_REST, INDIA_WS = "https://api.india.delta.exchange", "wss://socket.india.delta.exchange"
GLOBAL_REST, GLOBAL_WS = "https://api.delta.exchange", "wss://socket.delta.exchange"
RESOLUTIONS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "1d": 86400}
MAX_CANDLES = 2000  # per request, conservative [unverified]


def sign(secret: str, method: str, timestamp: str, path: str, query: str = "", body: str = "") -> str:
    msg = f"{method.upper()}{timestamp}{path}{query}{body}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def signed_headers(api_key: str, secret: str, method: str, timestamp: str, path: str,
                   query: str = "", body: str = "") -> Mapping[str, str]:
    return {"api-key": api_key, "timestamp": timestamp, "signature": sign(secret, method, timestamp, path, query, body),
            "User-Agent": "ofx/0.1", "Content-Type": "application/json"}


def capabilities(aggressor_verified: bool) -> Capabilities:
    return Capabilities(
        name="delta_exchange", trades=True, aggressor_flag=aggressor_verified, depth_levels=20,
        historical_trades=False, historical_candles=True, max_candles_per_request=MAX_CANDLES,
        notes="Public data. Aggressor from buyer_role/seller_role; EXACT only when verified on live payloads.")


def parse_trade(d: Mapping[str, Any], seq: int = 0, verified: bool = False) -> Trade:
    """One trade dict -> Trade. Timestamp may be microseconds (REST) or nanoseconds/seconds; normalise by magnitude."""
    raw = float(d.get("timestamp") or d.get("time") or 0)
    secs = raw / 1e6 if raw > 1e14 else raw / 1e3 if raw > 1e11 else raw
    if raw > 1e17:
        secs = raw / 1e9
    ts = datetime.fromtimestamp(secs, tz=UTC)
    if d.get("buyer_role") == "taker":
        side = AggressorSide.ASK
    elif d.get("seller_role") == "taker":
        side = AggressorSide.BID
    else:
        side = AggressorSide.UNKNOWN
    method = "exchange" if (verified and side is not AggressorSide.UNKNOWN) else ("unverified_exchange" if side is not AggressorSide.UNKNOWN else "none")
    return Trade(ts, float(d["price"]), float(d["size"] if d.get("size") is not None else d["quantity"]), side, seq, method)


def parse_l2(m: Mapping[str, Any], seq: int = 0) -> DepthSnapshot:
    """l2_orderbook message -> DepthSnapshot. Fields buy/sell [{limit_price, size}] per docs [unverified]."""
    bids = tuple(sorted((DepthLevel(float(x["limit_price"]), float(x["size"])) for x in m.get("buy", [])), key=lambda l: -l.price))
    asks = tuple(sorted((DepthLevel(float(x["limit_price"]), float(x["size"])) for x in m.get("sell", [])), key=lambda l: l.price))
    raw = float(m.get("timestamp") or 0)
    ts = datetime.fromtimestamp(raw / 1e6 if raw > 1e14 else raw / 1e3 if raw > 1e11 else raw, tz=UTC) if raw else datetime.now(UTC)
    return DepthSnapshot(ts, bids, asks, seq)


def parse_candles(rows: Sequence[Mapping[str, Any]]) -> list[Candle]:
    return sorted((Candle(datetime.fromtimestamp(int(r["time"]), tz=UTC), float(r["open"]), float(r["high"]),
                          float(r["low"]), float(r["close"]), float(r.get("volume") or 0)) for r in rows), key=lambda c: c.ts_open)


class DeltaProvider:
    def __init__(self, api_key: str = "", secret: str = "", *, base_url: str | None = None, ws_url: str | None = None,
                 client: httpx.AsyncClient | None = None, aggressor_verified: bool | None = None) -> None:
        self._key, self._secret = api_key, secret
        base = base_url or os.environ.get("DELTA_BASE_URL", INDIA_REST)
        self._ws = ws_url or os.environ.get("DELTA_WS_URL", INDIA_WS)
        self._http = client or httpx.AsyncClient(base_url=base, timeout=15)
        verified = aggressor_verified if aggressor_verified is not None else os.environ.get("DELTA_TAKER_VERIFIED") == "1"
        self.capabilities = capabilities(verified)
        self._verified = verified

    def __repr__(self) -> str:  # never leak credentials into logs
        return "DeltaProvider(api_key=***, secret=***)"

    async def _get(self, path: str, params: Mapping[str, Any] | None = None) -> Any:
        r = await self._http.get(path, params=params, headers={"User-Agent": "ofx/0.1", "Accept": "application/json"})
        j = r.json() if r.content else {}
        if r.status_code != 200 or j.get("success") is False:
            raise RuntimeError(f"delta request failed: {r.status_code} {str(j.get('error', ''))[:120]}")
        return j.get("result")

    async def instruments(self) -> Sequence[Instrument]:
        res = await self._get("/v2/products")
        return [Instrument(f"DELTA:{p['symbol']}", p["symbol"], "DELTA", float(p.get("tick_size") or 0.5), float(p.get("contract_value") or 1.0))
                for p in res if p.get("symbol")]

    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Candle]:
        if timeframe not in RESOLUTIONS:
            raise ProviderUnsupported(f"timeframe {timeframe}")
        step = RESOLUTIONS[timeframe] * MAX_CANDLES
        sym, out, cur = iid.split(":", 1)[-1], [], int(start.timestamp())
        while cur < int(end.timestamp()):
            nxt = min(int(end.timestamp()), cur + step)
            out += parse_candles(await self._get("/v2/history/candles", {"symbol": sym, "resolution": timeframe, "start": cur, "end": nxt}) or [])
            cur = nxt
        uniq = {c.ts_open: c for c in out}
        return [uniq[k] for k in sorted(uniq)]

    async def trades(self, iid: str, start: datetime, end: datetime) -> Sequence[Trade]:
        """Only RECENT public trades are available (no deep history). Filtered to [start, end)."""
        res = await self._get(f"/v2/trades/{iid.split(':', 1)[-1]}") or []
        out = [parse_trade(d, i, self._verified) for i, d in enumerate(res)]
        return sorted((t for t in out if start <= t.ts < end), key=lambda t: (t.ts, t.seq))

    def _subscribe_msg(self, iid: str, channel: str) -> str:
        return json.dumps({"type": "subscribe", "payload": {"channels": [{"name": channel, "symbols": [iid.split(":", 1)[-1]]}]}})

    async def stream_trades(self, iid: str) -> AsyncIterator[Trade]:  # pragma: no cover - needs a live socket
        import websockets
        seq = 0
        async with websockets.connect(self._ws, ping_interval=20) as ws:
            await ws.send(self._subscribe_msg(iid, "all_trades"))
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") in ("all_trades", "all_trades_snapshot") and "price" in m:
                    seq += 1
                    yield parse_trade(m, seq, self._verified)
                elif m.get("type") in ("all_trades_snapshot",):
                    for d in m.get("trades", []):
                        seq += 1
                        yield parse_trade(d, seq, self._verified)

    async def stream_depth(self, iid: str) -> AsyncIterator[DepthSnapshot]:  # pragma: no cover - needs a live socket
        import websockets
        seq = 0
        async with websockets.connect(self._ws, ping_interval=20) as ws:
            await ws.send(self._subscribe_msg(iid, "l2_orderbook"))
            async for raw in ws:
                m = json.loads(raw)
                if m.get("type") == "l2_orderbook" and ("buy" in m or "sell" in m):
                    seq += 1
                    yield parse_l2(m, seq)

    async def stream_quotes(self, iid: str) -> AsyncIterator[Quote]:  # pragma: no cover
        raise ProviderUnsupported("quote stream not implemented")
        yield
