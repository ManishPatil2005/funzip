import asyncio
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from ofx.main import create_app
from ofx.providers import demo_market as dm
from ofx.providers.synthetic import SyntheticProvider

MON = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)


def test_same_trades_regardless_of_query_window():
    full = dm.trades_between("SYN:NIFTY", MON, MON + timedelta(hours=8))
    part = dm.trades_between("SYN:NIFTY", MON + timedelta(hours=2), MON + timedelta(hours=3))
    ids = {(t.ts, t.price, t.qty, t.side) for t in full}
    assert part and all((t.ts, t.price, t.qty, t.side) in ids for t in part)  # a sub-window is an exact slice, never a different path


def test_weekend_has_no_trades_and_session_bounds():
    assert dm.trades_between("SYN:NIFTY", datetime(2026, 10, 10, 0, 0, tzinfo=UTC), datetime(2026, 10, 11, 23, 0, tzinfo=UTC)) == []
    tr = dm.trades_between("SYN:NIFTY", MON, MON + timedelta(hours=10))
    open_utc, close_utc = datetime(2026, 10, 5, 3, 45, tzinfo=UTC), datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    assert tr[0].ts >= open_utc and tr[-1].ts < close_utc  # 09:15-15:30 IST


def test_prices_on_tick_grid_and_realistic_scale():
    tr = dm.trades_between("SYN:NIFTY", MON, MON + timedelta(hours=10))
    assert all(abs(t.price / 0.05 - round(t.price / 0.05)) < 1e-6 for t in tr[:2000])
    lo, hi = min(t.price for t in tr), max(t.price for t in tr)
    assert 22000 < lo < hi < 23500 and 40 < hi - lo < 600  # a plausible one-day range, not a 100->47 collapse
    assert all(t.side.value in ("ask", "bid") for t in tr)


def test_delta_follows_price_direction():
    from ofx.orderflow.footprint import build_footprint
    bars = build_footprint(dm.trades_between("SYN:NIFTY", MON, MON + timedelta(hours=10)), 2.5, timedelta(minutes=15))
    up = [b.delta for b in bars if b.close_px > b.open_px]
    dn = [b.delta for b in bars if b.close_px < b.open_px]
    assert sum(up) / len(up) > 0 > sum(dn) / len(dn)


def test_instruments_endpoint_and_footprint_over_five_days():
    c = TestClient(create_app(api_key=""))
    ins = c.get("/api/v1/instruments").json()["instruments"]
    nifty = next(i for i in ins if i["iid"] == "SYN:NIFTY")
    assert nifty["session"] == "NSE" and nifty["tick_size"] == 0.05
    r = c.get("/api/v1/footprint?iid=SYN:NIFTY&tick=2.5&start=2026-10-05T03:00:00Z&end=2026-10-09T11:00:00Z&tf=15m&session=NSE")
    assert r.status_code == 200 and len(r.json()["bars"]) == 125  # 25 fifteen-minute bars x 5 sessions


def test_depth_and_candles_available_for_demo():
    p = SyntheticProvider()
    d = asyncio.run(p.depth_history("SYN:NIFTY", MON + timedelta(hours=1), MON + timedelta(hours=1, seconds=5)))
    assert len(d) == 5 and len(d[0].bids) == 20 and d[0].bids[0].price < d[0].asks[0].price
    cs = asyncio.run(p.candles("SYN:NIFTY", MON, MON + timedelta(hours=10), "30m"))
    assert len(cs) == 13  # 6h15m session = 13 half-hour candles


def test_vwap_session_profiles_and_buy_sell_totals():
    c = TestClient(create_app(api_key=""))
    q = "iid=SYN:NIFTY&tick=2.5&start=2026-10-05T03:00:00Z&end=2026-10-06T11:00:00Z"
    bars = c.get(f"/api/v1/footprint?{q}&tf=15m&session=NSE").json()["bars"]
    assert all(b["bid_volume"] + b["ask_volume"] == b["volume"] and b["vwap"] for b in bars)
    first_day = [b for b in bars if b["ts_open"].startswith("2026-10-05")]
    # first bar's VWAP is inside its own range, and VWAP resets at the next session open
    assert first_day[0]["low"] <= first_day[0]["vwap"] <= first_day[0]["high"]
    nxt = next(b for b in bars if b["ts_open"].startswith("2026-10-06"))
    assert nxt["low"] <= nxt["vwap"] <= nxt["high"]
    sp = c.get(f"/api/v1/session-profiles?{q}&session=NSE").json()["sessions"]
    assert len(sp) == 2
    day = sp[0]
    assert abs(sum(b + a for b, a in day["rows"].values()) - day["total"]) < 1e-6
    assert day["levels"]["val"] <= day["levels"]["poc"] <= day["levels"]["vah"]
    day1_vol = sum(b["volume"] for b in first_day)
    assert abs(day1_vol - day["total"]) < 1e-6  # the profile and the bars are built from the same trades
    mp_ = c.get(f"/api/v1/market-profile?{q}&session=NSE").json()["profiles"][0]
    assert mp_["period_minutes"] == 30 and mp_["n_periods"] == 13 and mp_["letters"]


def test_response_size_guard_rejects_too_many_rows(monkeypatch):
    monkeypatch.setattr("ofx.api.service.MAX_ROWS", 1000)
    c = TestClient(create_app(api_key=""))
    r = c.get("/api/v1/footprint?iid=SYN:NIFTY&tick=0.05&start=2026-10-05T03:00:00Z&end=2026-10-09T11:00:00Z&tf=30m&session=NSE")
    assert r.status_code == 400 and "row size" in r.json()["error"]
    assert c.get("/api/v1/footprint?iid=SYN:NIFTY&tick=50&start=2026-10-05T03:00:00Z&end=2026-10-06T11:00:00Z&tf=30m&session=NSE").status_code == 200


def test_closed_windows_are_cached_and_open_windows_are_not():
    from ofx.api.cache import MemoryCache
    from ofx.api.service import Service

    class Counting(SyntheticProvider):
        calls = 0

        async def trades(self, iid, start, end):  # type: ignore[no-untyped-def]
            Counting.calls += 1
            return await super().trades(iid, start, end)

    svc = Service(Counting(), MemoryCache(8), 60.0)
    s, e = datetime(2026, 10, 5, 3, 45, tzinfo=UTC), datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
    a = asyncio.run(svc.footprint("SYN:NIFTY", 5.0, s, e, "15m"))
    b = asyncio.run(svc.footprint("SYN:NIFTY", 5.0, s, e, "15m"))
    assert Counting.calls == 1 and a == b  # second call served from cache
    asyncio.run(svc.footprint("SYN:NIFTY", 10.0, s, e, "15m"))
    assert Counting.calls == 2  # a different row size is a different key
    now = datetime.now(UTC)
    asyncio.run(svc.footprint("SYN:NIFTY", 5.0, now - timedelta(hours=1), now + timedelta(minutes=5), "15m"))
    asyncio.run(svc.footprint("SYN:NIFTY", 5.0, now - timedelta(hours=1), now + timedelta(minutes=5), "15m"))
    assert Counting.calls == 4  # a window that has not closed is never cached
