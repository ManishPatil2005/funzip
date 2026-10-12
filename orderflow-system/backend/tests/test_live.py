import asyncio
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ofx.api.hub import Hub
from ofx.domain import AggressorSide as S
from ofx.ingest import LiveFootprint, StreamingTickRule, run_ingest
from ofx.main import create_app
from ofx.providers.base import Capabilities
from tests.conftest import tr

M1 = timedelta(minutes=1)


def test_tick_rule_stream_first_print_unknown_then_inherits():
    r = StreamingTickRule()
    a, b, c, d = (r(tr(i, p, 1, S.UNKNOWN, i, "none")) for i, p in enumerate((100, 101, 101, 100)))
    assert [x.side for x in (a, b, c, d)] == [S.UNKNOWN, S.ASK, S.ASK, S.BID]
    assert b.side_method == "tick_rule"


def test_live_footprint_closes_bars_and_carries_cvd():
    lf = LiveFootprint(1.0, M1)
    f1, c1 = lf.on_trade(tr(1, 100, 5, S.ASK, 1))
    assert c1 is None and f1.cvd_close == 5
    f2, c2 = lf.on_trade(tr(70, 100, 3, S.BID, 2))  # next minute
    assert c2 is not None and c2.cvd_close == 5 and f2.cvd_open == 5 and f2.cvd_close == 2
    with pytest.raises(ValueError):
        lf.on_trade(tr(10, 100, 1, S.ASK, 3))  # late trade


def test_run_ingest_publishes_forming_and_closed():
    class P:
        capabilities = Capabilities("fake", True, False, 0, False, False)

        async def stream_trades(self, iid):
            for i, (sec, px) in enumerate([(1, 100), (2, 101), (65, 101), (66, 100)]):
                yield tr(sec, px, 2, S.UNKNOWN, i, "none")

    hub = Hub()
    cl = hub.subscribe("X:footprint")
    n = asyncio.run(run_ingest(P(), "X", 1.0, M1, hub))
    msgs = []
    while not cl.queue.empty():
        msgs.append(cl.queue.get_nowait())
    assert n == 4 and sum(m["closed"] for m in msgs) == 1
    closed = next(m for m in msgs if m["closed"])["bar"]
    assert closed["quality"] == "estimated" and closed["volume"] == 4


Q = "iid=SYN:TEST&tick=0.5&start=2026-01-05T04:00:00Z&end=2026-01-05T04:02:00Z"


def test_heatmap_endpoint_shape_and_bounds():
    c = TestClient(create_app(api_key="", rate_per_min=0))
    j = c.get(f"/api/v1/heatmap?{Q}&dt=10").json()
    rows, cols = j["shape"]
    a = np.array(j["intensity"])
    assert a.shape == (rows, cols) and cols == 12 and 0 <= a.min() and a.max() <= 1 and a.max() > 0.9
    assert c.get(f"/api/v1/heatmap?{Q}&dt=10&scale=bogus").status_code == 400
    assert c.get(f"/api/v1/heatmap?{Q}&dt=0").status_code == 422


def test_heatmap_too_large_rejected():
    c = TestClient(create_app(api_key="", rate_per_min=0))
    assert c.get("/api/v1/heatmap?iid=x&tick=0.5&start=2026-01-05T00:00:00Z&end=2026-01-06T00:00:00Z&dt=0.5").status_code == 400  # 1-day span exceeds the 6 h cap


def test_rate_limit_returns_429_but_not_for_health():
    c = TestClient(create_app(api_key="", rate_per_min=3))
    codes = [c.get("/api/v1/capabilities").status_code for _ in range(6)]
    assert codes[:3] == [200, 200, 200] and 429 in codes[3:]
    assert c.get("/health").status_code == 200


def test_lifespan_live_ingest_publishes(monkeypatch):
    monkeypatch.setenv("OFX_LIVE_IID", "SYN:TEST")
    app = create_app(api_key="", rate_per_min=0)
    cl = app.state.hub.subscribe("SYN:TEST:footprint")  # subscribe first: the synthetic stream bursts instantly
    with TestClient(app) as c:
        import time
        for _ in range(50):
            if not cl.queue.empty():
                break
            time.sleep(0.05)
        assert not cl.queue.empty() and cl.queue.get_nowait()["type"] == "footprint"
        assert c.get("/health").status_code == 200


def test_recorder_batches_and_persists_closed_bars():
    from ofx.ingest import Recorder

    class Fake:
        def __init__(self):
            self.trades, self.bars = [], []

        def insert_trades(self, iid, ts):
            self.trades += list(ts)

        def upsert_bar(self, iid, tf, bar, closed):
            self.bars.append((iid, tf, closed))

    class P:
        capabilities = Capabilities("fake", True, True, 0, False, False)

        async def stream_trades(self, iid):
            for i, sec in enumerate((1, 2, 65, 66)):
                yield tr(sec, 100, 1, S.ASK, i)

    fake, hub = Fake(), Hub()
    rec = Recorder(fake, "X", "1m", batch=100)
    asyncio.run(run_ingest(P(), "X", 1.0, M1, hub, on_closed=rec.on_closed, on_trade=rec.on_trade))
    rec.flush()
    assert len(fake.trades) == 4 and fake.bars == [("X", "1m", True)]


def test_export_csv_and_json():
    c = TestClient(create_app(api_key="", rate_per_min=0))
    r = c.get("/api/v1/export/footprint?iid=SYN:TEST&tick=0.5&start=2026-01-05T04:00:00Z&end=2026-01-05T04:10:00Z&tf=5m")
    lines = r.text.strip().splitlines()
    assert r.headers["content-type"].startswith("text/csv") and lines[0].startswith("ts_open,row,price") and len(lines) > 5
    assert c.get("/api/v1/export/footprint?iid=x&tick=1&start=2026-01-05T04:00:00Z&end=2026-01-05T04:10:00Z&format=xml").status_code == 400


def test_live_footprint_session_alignment_and_cvd_reset():
    from datetime import timedelta as td

    from ofx.orderflow.market_profile import NSE_EQUITY, bar_align_offset
    tf = td(minutes=30)
    lf = LiveFootprint(1.0, tf, lambda ts: NSE_EQUITY.session_start(ts), align_offset=bar_align_offset(NSE_EQUITY, tf))
    f, _ = lf.on_trade(tr(0, 100, 5, S.ASK, 1))  # T0 = 04:00 UTC = 09:30 IST
    assert (f.ts_open.hour, f.ts_open.minute) == (3, 45)  # bar opened at 09:15 IST, not at 09:30
    f2, closed = lf.on_trade(tr(3600 * 24, 100, 2, S.ASK, 2))  # next day: new session
    assert closed is not None and f2.cvd_open == 0  # CVD reset at the session change
