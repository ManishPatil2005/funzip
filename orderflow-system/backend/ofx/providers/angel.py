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

from ofx.domain import Candle, Instrument, Trade
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


class AngelAuthError(RuntimeError):
    pass


def credentials_from_env(env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if env is None else env
    missing = [k for k in REQUIRED_ENV if not env.get(k)]
    if missing:
        raise AngelAuthError(f"missing environment variables: {', '.join(missing)}")
    return {k: env[k] for k in REQUIRED_ENV}


def parse_candles(rows: Sequence[Sequence], ) -> list[Candle]:
    """Rows are [iso_ts_with_offset, o, h, l, c, v]."""
    out = []
    for r in rows:
        ts = datetime.fromisoformat(str(r[0]))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=IST)
        out.append(Candle(ts.astimezone(UTC), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])))
    return sorted(out, key=lambda c: c.ts_open)


class AngelProvider:
    capabilities = CAPABILITIES

    def __init__(self, creds: Mapping[str, str], tokens: Mapping[str, tuple[str, str]] | None = None,
                 client: httpx.AsyncClient | None = None, clock=None) -> None:
        self._c = dict(creds)
        self._tokens = dict(tokens or {})  # iid -> (exchange, symboltoken)
        self._http = client or httpx.AsyncClient(base_url=BASE, timeout=15)
        self._jwt: str | None = None
        self._clock = clock

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

    async def instruments(self) -> Sequence[Instrument]:
        return [Instrument(iid, iid.split(":")[-1], ex, 0.05) for iid, (ex, _tok) in self._tokens.items()]

    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Candle]:
        if timeframe not in INTERVALS:
            raise ProviderUnsupported(f"timeframe {timeframe}")
        if iid not in self._tokens:
            raise ProviderUnsupported(f"no symbol token configured for {iid}")
        if self._jwt is None:
            await self.login()
        name, secs = INTERVALS[timeframe]
        exch, tok = self._tokens[iid]
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

    async def stream_trades(self, iid: str) -> AsyncIterator[Trade]:  # pragma: no cover - needs live session
        raise ProviderUnsupported("live stream wiring requires the SmartAPI websocket SDK and a live session [unverified]")
        yield  # makes this an async generator

    stream_depth = stream_quotes = stream_trades  # type: ignore[assignment]
