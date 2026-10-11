import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from ofx.providers import angel
from ofx.providers.totp import totp

CREDS = {"ANGEL_SMARTAPI_KEY": "k-key", "ANGEL_CLIENT_ID": "C123", "ANGEL_PIN": "9999", "ANGEL_TOTP_SECRET": "JBSWY3DPEHPK3PXP"}


def test_totp_rfc6238_vectors():
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # ASCII "12345678901234567890" (RFC 6238 SHA-1 seed)
    assert totp(secret, at=59, digits=8) == "94287082"
    assert totp(secret, at=1111111109, digits=8) == "07081804"


def mock(handler):
    return httpx.AsyncClient(base_url=angel.BASE, transport=httpx.MockTransport(handler))


def test_login_and_paginated_candles():
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        body = json.loads(req.content)
        calls.append((req.url.path, body))
        if req.url.path == angel.LOGIN:
            assert body["clientcode"] == "C123" and len(body["totp"]) == 6
            return httpx.Response(200, json={"status": True, "data": {"jwtToken": "jwt-abc"}})
        assert req.headers["authorization"] == "Bearer jwt-abc" and req.headers["x-privatekey"] == "k-key"
        return httpx.Response(200, json={"status": True, "data": [["2026-01-05T09:15:00+05:30", 100, 101, 99, 100.5, 1000]]})

    async def run():
        p = angel.AngelProvider(CREDS, {"NSE:TEST": ("NSE", "1234")}, mock(handler))
        return await p.candles("NSE:TEST", datetime(2026, 1, 5, 3, 0, tzinfo=UTC), datetime(2026, 1, 12, 3, 0, tzinfo=UTC), "5m")

    out = asyncio.run(run())
    assert calls[0][0] == angel.LOGIN and len([c for c in calls if c[0] == angel.CANDLES]) >= 4  # 7 days / (500*5m) windows
    assert out[0].ts_open == datetime(2026, 1, 5, 3, 45, tzinfo=UTC) and len(out) == 1  # duplicates across windows collapse


def test_login_failure_never_leaks_secrets():
    def handler(req):
        return httpx.Response(401, json={"status": False, "message": "Invalid totp"})

    async def run():
        p = angel.AngelProvider(CREDS, {}, mock(handler))
        await p.login()

    with pytest.raises(angel.AngelAuthError) as e:
        asyncio.run(run())
    s = str(e.value)
    assert "Invalid totp" in s and "9999" not in s and "JBSWY3DPEHPK3PXP" not in s


def test_env_validation_and_repr():
    with pytest.raises(angel.AngelAuthError) as e:
        angel.credentials_from_env({"ANGEL_CLIENT_ID": "x"})
    assert "ANGEL_PIN" in str(e.value)
    assert "9999" not in repr(angel.AngelProvider(CREDS))


def test_no_historical_trades():
    from ofx.providers.base import ProviderUnsupported
    with pytest.raises(ProviderUnsupported):
        asyncio.run(angel.AngelProvider(CREDS).trades("x", datetime.now(UTC), datetime.now(UTC)))


def test_ticks_to_trade_volume_delta_and_quote_rule():
    st: dict = {}
    base = {"last_traded_price": 10050, "volume_trade_for_the_day": 1000, "exchange_timestamp": 1_767_600_000_000,
            "best_5_buy_data": [{"price": 10040}], "best_5_sell_data": [{"price": 10050}]}
    assert angel.ticks_to_trade(base, st) is None  # first tick primes state
    t = angel.ticks_to_trade({**base, "volume_trade_for_the_day": 1030}, st)
    assert t.qty == 30 and t.price == 100.5 and t.side.value == "ask" and t.side_method == "quote_rule"
    assert angel.ticks_to_trade({**base, "volume_trade_for_the_day": 1030}, st) is None  # no new volume
    mid = angel.ticks_to_trade({**base, "last_traded_price": 10045, "volume_trade_for_the_day": 1040}, st)
    assert mid.side.value == "unknown" and mid.side_method == "none"  # inside the spread: never guessed
    crossed = {**base, "best_5_buy_data": [{"price": 10060}], "volume_trade_for_the_day": 1050}
    assert angel.ticks_to_trade(crossed, st).side.value == "unknown"  # crossed book ignored
