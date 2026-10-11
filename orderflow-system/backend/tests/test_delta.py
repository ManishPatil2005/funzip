import asyncio
from datetime import UTC, datetime

import httpx

from ofx.domain import AggressorSide as S
from ofx.providers import angel, delta


def mock(handler):
    return httpx.AsyncClient(base_url=delta.INDIA_REST, transport=httpx.MockTransport(handler))


def test_parse_trade_roles_and_timestamp_units():
    t = delta.parse_trade({"price": "100.5", "size": 3, "buyer_role": "taker", "seller_role": "maker", "timestamp": 1_767_600_000_000_000}, 1, True)
    assert t.side is S.ASK and t.side_method == "exchange" and t.qty == 3 and t.ts == datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    u = delta.parse_trade({"price": 1, "size": 1, "buyer_role": "maker", "seller_role": "taker", "timestamp": 1_767_600_000}, 2, False)
    assert u.side is S.BID and u.side_method == "unverified_exchange"
    assert delta.parse_trade({"price": 1, "size": 1, "timestamp": 1_767_600_000}).side is S.UNKNOWN


def test_quality_depends_on_verification():
    assert delta.DeltaProvider(aggressor_verified=False).capabilities.trade_quality.value == "estimated"
    assert delta.DeltaProvider(aggressor_verified=True).capabilities.trade_quality.value == "exact"


def test_instruments_candles_trades_via_mock():
    def handler(req: httpx.Request) -> httpx.Response:
        assert "api-key" not in req.headers  # public data: no credentials sent
        if req.url.path == "/v2/products":
            return httpx.Response(200, json={"success": True, "result": [{"symbol": "BTCUSD", "tick_size": "0.5", "contract_value": "0.001"}]})
        if req.url.path == "/v2/history/candles":
            return httpx.Response(200, json={"success": True, "result": [{"time": 1_767_600_000, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}]})
        if req.url.path == "/v2/trades/BTCUSD":
            return httpx.Response(200, json={"success": True, "result": [
                {"price": "100", "size": 2, "buyer_role": "taker", "seller_role": "maker", "timestamp": 1_767_600_001_000_000},
                {"price": "99.5", "size": 1, "buyer_role": "maker", "seller_role": "taker", "timestamp": 1_767_600_002_000_000}]})
        return httpx.Response(404, json={"success": False, "error": "nope"})

    async def run():
        p = delta.DeltaProvider(client=mock(handler), aggressor_verified=True)
        ins = await p.instruments()
        c = await p.candles("DELTA:BTCUSD", datetime(2026, 1, 5, 8, 0, tzinfo=UTC), datetime(2026, 1, 5, 9, 0, tzinfo=UTC), "5m")
        t = await p.trades("DELTA:BTCUSD", datetime(2026, 1, 5, 8, 0, tzinfo=UTC), datetime(2026, 1, 5, 9, 0, tzinfo=UTC))
        return ins, c, t

    ins, c, t = asyncio.run(run())
    assert ins[0].iid == "DELTA:BTCUSD" and ins[0].tick_size == 0.5
    assert len(c) == 1 and c[0].close == 1.5
    assert [x.side for x in t] == [S.ASK, S.BID]


def test_signing_and_repr():
    assert delta.signed_headers("k", "s3", "GET", "1", "/p")["signature"] == delta.sign("s3", "GET", "1", "/p")
    assert "s3" not in repr(delta.DeltaProvider("k", "s3"))


def test_angel_password_alias():
    env = {"ANGEL_SMARTAPI_KEY": "a", "ANGEL_CLIENT_ID": "b", "ANGEL_PASSWORD": "c", "ANGEL_TOTP_SECRET": "d"}
    assert angel.credentials_from_env(env)["ANGEL_PIN"] == "c"


def test_parse_l2_sorts_best_first():
    from ofx.providers.delta import parse_l2
    s = parse_l2({"buy": [{"limit_price": "99", "size": 5}, {"limit_price": "100", "size": 2}],
                  "sell": [{"limit_price": "102", "size": 1}, {"limit_price": "101", "size": 3}], "timestamp": 1_767_600_000_000_000}, 7)
    assert [l.price for l in s.bids] == [100, 99] and [l.price for l in s.asks] == [101, 102] and s.seq == 7
