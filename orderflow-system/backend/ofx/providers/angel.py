"""Angel One SmartAPI adapter (REST: login + historical candles; stream via official SDK).

Verified only against MOCKED responses (see tests). Endpoint paths, header names and payload
shapes follow the public SmartAPI documentation as I know it and MUST be confirmed with a real
login before relying on them [UNVERIFIED]. Credentials are read from the environment by name:
ANGEL_SMARTAPI_KEY, ANGEL_CLIENT_ID, ANGEL_PIN, ANGEL_TOTP_SECRET. No value is ever logged.

Honest capability statement:
  * No exchange aggressor flag, snapshot-style ticks => delta/footprint are ESTIMATED.
  * Depth is 5 levels (20-level mode is beta). Historical candles are capped per request.
  * No historical trade/tick history.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from ofx.domain import AggressorSide, Candle, Instrument, Trade
from ofx.providers.angel_master import MasterCache, Scrip
from ofx.providers.angel_master import search as master_search
from ofx.providers.base import Capabilities, ProviderUnsupported
from ofx.providers.totp import totp

BASE = "https://apiconnect.angelone.in"
LOGIN = "/rest/auth/angelbroking/user/v1/loginByPassword"
CANDLES = "/rest/secure/angelbroking/historical/v1/getCandleData"
IST = ZoneInfo("Asia/Kolkata")

CAPABILITIES = Capabilities(
    name="angel_one", trades=True, aggressor_flag=False, depth_levels=5, historical_trades=False,
    historical_candles=True, max_candles_per_request=500,
    notes="Snapshot ticks; side estimated via quote rule. Limits unverified where marked in docs.")

REQUIRED_ENV = ("ANGEL_SMARTAPI_KEY", "ANGEL_CLIENT_ID", "ANGEL_PIN", "ANGEL_TOTP_SECRET")

INTERVALS = {"1m": ("ONE_MINUTE", 60), "5m": ("FIVE_MINUTE", 300), "15m": ("FIFTEEN_MINUTE", 900),
             "30m": ("THIRTY_MINUTE", 1800), "1h": ("ONE_HOUR", 3600), "1d": ("ONE_DAY", 86400)}


# Shown before any search. Index tokens are recalled from Angel docs and UNVERIFIED; SBIN (3045) was confirmed by the smoke test.
DEFAULT_TOKENS: dict[str, tuple[str, str]] = {
    "NSE:Nifty 50": ("NSE", "99926000"), "NSE:Nifty Bank": ("NSE", "99926009"),
    "NSE:SBIN-EQ": ("NSE", "3045"), "NSE:RELIANCE-EQ": ("NSE", "2885"),
}


class AngelAuthError(RuntimeError):
    pass


def credentials_from_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if env is None else env
    merged = dict(env)
    if not merged.get("ANGEL_PIN") and merged.get("ANGEL_PASSWORD"):  # accepted alias: Angel calls the PIN "password"
        merged["ANGEL_PIN"] = merged["ANGEL_PASSWORD"]
    missing = [k for k in REQUIRED_ENV if not merged.get(k)]
    if missing:
        raise AngelAuthError(f"missing environment variables: {', '.join(missing)}")
    return {k: merged[k] for k in REQUIRED_ENV}


def parse_candles(rows: Sequence[Sequence], ) -> list[Candle]:
    """Rows are [iso_ts_with_offset, o, h, l, c, v]."""
    out = []
    for r in rows:
        ts = datetime.fromisoformat(str(r[0]))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=IST)
        out.append(Candle(ts.astimezone(UTC), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    return sorted(out, key=lambda c: c.ts_open)


EXCHANGE_TYPE = {"NSE": 1, "NFO": 2, "BSE": 3, "BFO": 4, "MCX": 5, "NCDEX": 7, "CDS": 13}  # per SmartAPI docs [unverified]


def ticks_to_trade(tick: Mapping, state: dict) -> Trade | None:
    """Convert one SDK tick dict to a Trade, or None when no new volume traded.

    Prices arrive in paise (divide by 100). qty = increase in day volume since the previous tick; the
    first tick only primes the state. Side = quote rule: last price >= best ask -> ASK, <= best bid -> BID,
    otherwise UNKNOWN (never guessed).
    """
    vol = tick.get("volume_trade_for_the_day")
    ltp = tick.get("last_traded_price")
    if vol is None or ltp is None:
        return None
    prev, state["vol"] = state.get("vol"), vol
    if prev is None or vol <= prev:
        return None
    px = float(ltp) / 100.0
    bids, asks = tick.get("best_5_buy_data") or [], tick.get("best_5_sell_data") or []
    side = AggressorSide.UNKNOWN
    if bids and asks:
        bid, ask = float(bids[0]["price"]) / 100.0, float(asks[0]["price"]) / 100.0
        if bid < ask:
            side = AggressorSide.ASK if px >= ask else AggressorSide.BID if px <= bid else AggressorSide.UNKNOWN
    ms = tick.get("exchange_timestamp")
    ts = datetime.fromtimestamp(ms / 1000.0, tz=UTC) if ms else datetime.now(UTC)
    state["seq"] = state.get("seq", 0) + 1
    return Trade(ts, px, float(vol - prev), side, state["seq"], "quote_rule" if side is not AggressorSide.UNKNOWN else "none")


class AngelProvider:
    capabilities = CAPABILITIES

    def __init__(self, creds: Mapping[str, str], tokens: Mapping[str, tuple[str, str]] | None = None,
                 client: httpx.AsyncClient | None = None, clock=None) -> None:
        self._c = dict(creds)
        self._tokens = dict(tokens or DEFAULT_TOKENS)  # iid -> (exchange, symboltoken)
        self._http = client or httpx.AsyncClient(base_url=BASE, timeout=15)
        self._jwt: str | None = None
        self._feed_token: str | None = None
        self._clock = clock
        self._master = MasterCache()

    def __repr__(self) -> str:
        return "AngelProvider(credentials=***)"

    def _headers(self, auth: bool) -> dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json", "X-UserType": "USER",
             "X-SourceID": "WEB", "X-ClientLocalIP": "127.0.0.1", "X-ClientPublicIP": "127.0.0.1",
             "X-MACAddress": "00:00:00:00:00:00", "X-PrivateKey": self._c["ANGEL_SMARTAPI_KEY"]}
        if auth and self._jwt:
            h["Authorization"] = f"Bearer {self._jwt}"
        return h

    async def login(self) -> None:
        body = {"clientcode": self._c["ANGEL_CLIENT_ID"], "password": self._c["ANGEL_PIN"],
                "totp": totp(self._c["ANGEL_TOTP_SECRET"], self._clock() if self._clock else None)}
        r = await self._http.post(LOGIN, json=body, headers=self._headers(False))
        j = r.json() if r.content else {}
        if r.status_code != 200 or not j.get("status"):
            # Message only: never echo the request body (it holds the PIN and TOTP).
            raise AngelAuthError(f"login failed: {j.get('message', r.status_code)}")
        self._jwt = j["data"]["jwtToken"]
        self._feed_token = j["data"].get("feedToken")

    async def instruments(self) -> Sequence[Instrument]:
        return [Instrument(iid, iid.split(":")[-1], ex, 0.05) for iid, (ex, _tok) in self._tokens.items()]

    async def search(self, q: str, limit: int = 20) -> list[Instrument]:
        """Search the Angel instrument master; results can be charted immediately (tokens resolve lazily)."""
        found = master_search(await self._master.scrips(), q, limit)
        return [Instrument(f.iid, f.symbol, f.exchange, f.tick_size, f.lot_size, "Asia/Kolkata") for f in found]

    async def _resolve(self, iid: str) -> tuple[str, str]:
        if iid in self._tokens:
            return self._tokens[iid]
        sc: Scrip | None = await self._master.get(iid)
        if sc is None:
            raise ProviderUnsupported(f"unknown instrument {iid}; search for it first")
        self._tokens[iid] = (sc.exchange, sc.token)
        return self._tokens[iid]

    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Candle]:
        if timeframe not in INTERVALS:
            raise ProviderUnsupported(f"timeframe {timeframe}")
        exch, tok = await self._resolve(iid)
        if self._jwt is None:
            await self.login()
        name, secs = INTERVALS[timeframe]
        step = timedelta(seconds=secs * CAPABILITIES.max_candles_per_request)  # respect the per-request cap
        out: list[Candle] = []
        cur = start
        while cur < end:
            nxt = min(end, cur + step)
            body = {"exchange": exch, "symboltoken": tok, "interval": name,
                    "fromdate": cur.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
                    "todate": nxt.astimezone(IST).strftime("%Y-%m-%d %H:%M")}
            r = await self._http.post(CANDLES, json=body, headers=self._headers(True))
            j = r.json() if r.content else {}
            if r.status_code != 200 or not j.get("status"):
                raise RuntimeError(f"candle request failed: {j.get('message', r.status_code)}")
            out += parse_candles(j.get("data") or [])
            cur = nxt
        uniq = {c.ts_open: c for c in out}
        return [uniq[k] for k in sorted(uniq)]

    async def trades(self, iid: str, start: datetime, end: datetime) -> Sequence[Trade]:
        raise ProviderUnsupported("Angel One offers no historical trades; record live ticks forward instead")

    async def stream_trades(self, iid: str) -> AsyncIterator[Trade]:  # pragma: no cover - needs a live session
        """Live ticks via the official SmartAPI websocket SDK (lazy import, runs in its own thread).

        Snapshot feed => a 'trade' is inferred from the rise in day volume between snapshots (see
        ticks_to_trade). Side comes from the quote rule against the best bid/ask in the same tick, so
        data quality is ESTIMATED. SDK callback shapes are UNVERIFIED until run against a live session.
        """
        import asyncio

        from SmartApi.smartWebSocketV2 import SmartWebSocketV2  # type: ignore[import-not-found]

        if self._jwt is None:
            await self.login()
        exch, tok = await self._resolve(iid)
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue()
        feed_token = self._feed_token
        ws = SmartWebSocketV2(self._jwt, self._c["ANGEL_SMARTAPI_KEY"], self._c["ANGEL_CLIENT_ID"], feed_token)
        ws.on_data = lambda _w, msg: loop.call_soon_threadsafe(q.put_nowait, msg)
        # SDK errors and closes are surfaced into the stream so the reconnect wrapper sees them; a dropped
        # session also clears the JWT so the next attempt logs in again (tokens expire overnight).
        ws.on_error = lambda _w, *a: loop.call_soon_threadsafe(q.put_nowait, ConnectionError(f"websocket error: {a[-1] if a else ''}"))
        ws.on_close = lambda _w, *a: loop.call_soon_threadsafe(q.put_nowait, ConnectionError("websocket closed"))
        ws.on_open = lambda _w: ws.subscribe("ofx", 3, [{"exchangeType": EXCHANGE_TYPE[exch], "tokens": [tok]}])
        task = loop.run_in_executor(None, ws.connect)
        state: dict = {"vol": None, "seq": 0}
        try:
            while True:
                tick = await q.get()
                if isinstance(tick, BaseException):
                    self._jwt = None
                    raise tick
                tr = ticks_to_trade(tick, state)
                if tr is not None:
                    yield tr
        finally:
            ws.close_connection()
            task.cancel()

    stream_depth = stream_quotes = stream_trades  # type: ignore[assignment]
