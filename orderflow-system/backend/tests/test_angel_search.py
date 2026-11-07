import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ofx.domain import Candle
from ofx.main import create_app
from ofx.providers.angel import AngelProvider
from ofx.providers.angel_master import MasterCache, parse_master, search
from ofx.providers.base import Capabilities, ProviderUnsupported

ROWS = [
    {"token": "2885", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "expiry": "", "lotsize": "1", "instrumenttype": "", "exch_seg": "NSE", "tick_size": "5.000000"},
    {"token": "99926000", "symbol": "Nifty 50", "name": "NIFTY", "expiry": "", "lotsize": "1", "instrumenttype": "AMXIDX", "exch_seg": "NSE", "tick_size": "0.000000"},
    {"token": "26000", "symbol": "NIFTY25NOV26FUT", "name": "NIFTY", "expiry": "25NOV2026", "lotsize": "75", "instrumenttype": "FUTIDX", "exch_seg": "NFO", "tick_size": "5.000000"},
    {"token": "500325", "symbol": "RELIANCE-EQ", "name": "RELIANCE", "expiry": "", "lotsize": "1", "instrumenttype": "", "exch_seg": "BSE", "tick_size": "5.000000"},
    {"token": "1", "symbol": "RELIANCE25NOV2600CE", "name": "RELIANCE", "expiry": "", "lotsize": "250", "instrumenttype": "OPTSTK", "exch_seg": "NFO", "tick_size": "5.000000"},
    {"token": "", "symbol": "BROKEN", "exch_seg": "NSE"},
]


def test_parse_keeps_only_charting_instruments_and_converts_tick():
    s = parse_master(ROWS)
    assert {x.iid for x in s} == {"NSE:RELIANCE-EQ", "NSE:Nifty 50", "NFO:NIFTY25NOV26FUT", "BSE:RELIANCE-EQ"}  # options and broken rows dropped
    assert next(x for x in s if x.iid == "NSE:RELIANCE-EQ").tick_size == 0.05
    assert next(x for x in s if x.kind == "index").tick_size == 0.05  # 0 in the file -> default


def test_search_ranks_exact_then_index_before_future():
    s = parse_master(ROWS)
    assert [x.iid for x in search(s, "nifty")][:2] == ["NSE:Nifty 50", "NFO:NIFTY25NOV26FUT"]
    assert search(s, "reliance")[0].exchange in ("NSE", "BSE")
    assert search(s, "   ") == [] and search(s, "zzzz") == []


def provider():
    p = AngelProvider({"ANGEL_SMARTAPI_KEY": "k", "ANGEL_CLIENT_ID": "c", "ANGEL_PIN": "p", "ANGEL_TOTP_SECRET": "JBSWY3DPEHPK3PXP"})

    async def loader():
        return ROWS
    p._master = MasterCache(loader)
    return p


def test_provider_search_and_lazy_token_resolution():
    p = provider()
    res = asyncio.run(p.search("reliance"))
    assert res and res[0].tick_size == 0.05
    assert asyncio.run(p._resolve("BSE:RELIANCE-EQ")) == ("BSE", "500325")  # not preconfigured: resolved from the master
    with pytest.raises(ProviderUnsupported):
        asyncio.run(p._resolve("NSE:NOPE-EQ"))
    assert {"NSE:Nifty 50", "NSE:SBIN-EQ"} <= {i.iid for i in asyncio.run(p.instruments())}  # defaults include NIFTY


class CandleOnly:
    capabilities = Capabilities("candle_only", True, False, 0, False, True)

    async def instruments(self):
        return []

    async def trades(self, iid, start, end):
        raise ProviderUnsupported("no ticks")

    async def candles(self, iid, start, end, tf):
        t0 = datetime(2026, 1, 5, 3, 45, tzinfo=UTC)
        return [Candle(t0 + timedelta(minutes=5 * i), 100 + i, 102 + i, 99 + i, 101 + i, 1000.0) for i in range(4)]


def test_candle_only_provider_gets_honest_bars_instead_of_an_error():
    c = TestClient(create_app(CandleOnly(), api_key="", rate_per_min=0))
    r = c.get("/api/v1/footprint?iid=X&tick=0.05&start=2026-01-05T03:00:00Z&end=2026-01-05T05:00:00Z&tf=5m")
    assert r.status_code == 200
    j = r.json()
    b = j["bars"][0]
    assert j["data_quality"] == "bar_approximated" and len(j["bars"]) == 4
    assert b["rows"] == {} and b["delta"] == 0 and b["bid_volume"] == 0 and b["ask_volume"] == 0 and b["unknown_share"] == 1.0  # no invented split
    assert b["volume"] == 1000.0 and b["ts_close"] > b["ts_open"]


def test_search_endpoint_default_filters_instruments():
    c = TestClient(create_app(api_key="", rate_per_min=0))
    j = c.get("/api/v1/instruments/search?q=nif").json()
    assert any("NIFTY" in i["symbol"] for i in j["instruments"])
    assert c.get("/api/v1/instruments/search?q=").status_code == 422


def test_recent_only_provider_reports_where_coverage_starts():
    from ofx.providers.synthetic import SyntheticProvider
    from tests.conftest import T0
    class Recent(SyntheticProvider):
        recent_trades_only = True
        async def trades(self, iid, start, end):
            return [t for t in await super().trades(iid, start, end) if t.ts >= T0 + timedelta(hours=1)]
    c = TestClient(create_app(Recent(), api_key="", rate_per_min=0))
    r = c.get("/api/v1/footprint?iid=SYN:TEST&tick=1&start=2026-01-05T04:00:00Z&end=2026-01-05T06:00:00Z&tf=5m").json()
    assert r["coverage_start"] is not None and r["coverage_start"] >= "2026-01-05T05:00:00"
