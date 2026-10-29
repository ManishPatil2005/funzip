
from fastapi.testclient import TestClient

from ofx.api.cache import MemoryCache
from ofx.api.hub import Hub
from ofx.domain import DataQuality
from ofx.main import create_app
from ofx.providers import delta
from ofx.providers.base import Capabilities

Q = "iid=SYN:TEST&tick=0.5&start=2026-01-05T04:00:00Z&end=2026-01-05T04:30:00Z"


def client(key=""):
    return TestClient(create_app(api_key=key))


def test_health_and_footprint():
    c = client()
    assert c.get("/health").json() == {"status": "ok"}
    r = c.get(f"/api/v1/footprint?{Q}&tf=5m")
    assert r.status_code == 200
    j = r.json()
    assert j["data_quality"] == "exact" and len(j["bars"]) == 6 and "rows" in j["bars"][0]


def test_validation_errors():
    c = client()
    assert c.get(f"/api/v1/footprint?{Q}&tf=7m").status_code == 400
    assert c.get("/api/v1/footprint?iid=x&tick=0&start=2026-01-05T04:00:00Z&end=2026-01-05T05:00:00Z").status_code == 422
    assert c.get("/api/v1/footprint?iid=x&tick=1&start=2026-01-05T04:00:00Z&end=2026-01-13T05:00:00Z").status_code == 400
    assert c.get("/api/v1/footprint?iid=x&tick=1&start=2026-01-05T04:00:00&end=2026-01-05T05:00:00").status_code == 400  # naive time


def test_api_key_enforced():
    c = client("s3cret")
    assert c.get("/api/v1/capabilities").status_code == 401
    assert c.get("/api/v1/capabilities", headers={"x-api-key": "wrong"}).status_code == 401
    assert c.get("/api/v1/capabilities", headers={"x-api-key": "s3cret"}).status_code == 200
    assert c.get("/health").status_code == 200  # liveness stays open


def test_profiles_and_observations_language_clean():
    c = client()
    assert c.get(f"/api/v1/volume-profile?{Q}").json()["levels"]["poc"] > 0
    j = c.get(f"/api/v1/observations?{Q}&tf=1m").json()
    from ofx.language import lint
    for o in j["observations"]:
        assert lint(o["summary"]) == [] and o["data_quality"] and "limitations" in o


def test_market_profile_endpoint():
    j = client().get(f"/api/v1/market-profile?{Q.replace('04:00:00Z', '03:45:00Z').replace('04:30:00Z', '05:45:00Z')}&session=CRYPTO").json()
    assert "profiles" in j


def test_cache_ttl_and_eviction():
    c = MemoryCache(max_items=2)
    c.set("a", 1, 60); c.set("b", 2, 60); c.set("c", 3, 60)
    assert c.get("a") is None and c.get("c") == 3
    c.set("z", 1, -1)
    assert c.get("z") is None


def test_hub_drops_oldest_for_slow_client():
    h = Hub(queue_size=2)
    cl = h.subscribe("t")
    for i in range(4):
        h.publish("t", {"i": i})
    got = [cl.queue.get_nowait()["i"] for _ in range(2)]
    assert got == [2, 3] and cl.dropped == 2


def test_websocket_receives_published():
    app = create_app(api_key="")
    c = TestClient(app)
    with c.websocket_connect("/ws/v1/stream?topic=t1") as ws:
        app.state.hub.publish("t1", {"hello": 1})
        assert ws.receive_json()["hello"] == 1


def test_delta_signing_is_deterministic_and_secret_not_in_repr():
    h = delta.signed_headers("k", "hunter2", "GET", "1700000000", "/v2/products")
    assert h["signature"] == delta.sign("hunter2", "GET", "1700000000", "/v2/products")
    assert "hunter2" not in repr(delta.DeltaProvider("k", "hunter2"))
    assert Capabilities("x", True, False, 0, False, False).trade_quality is DataQuality.ESTIMATED


def test_session_alignment_nse_30m_bars_start_at_0915_ist():
    from datetime import UTC, datetime, timedelta

    from ofx.orderflow.market_profile import MCX_COMMODITY, NSE_EQUITY, bar_align_offset
    assert bar_align_offset(NSE_EQUITY, timedelta(minutes=30)) == timedelta(minutes=15)  # 03:45 UTC -> :15/:45 boundaries
    assert bar_align_offset(NSE_EQUITY, timedelta(hours=1)) == timedelta(minutes=45)
    assert bar_align_offset(MCX_COMMODITY, timedelta(hours=1)) == timedelta(minutes=30)
    c = client()
    q = "iid=SYN:TEST&tick=0.5&start=2026-01-05T03:45:00Z&end=2026-01-05T05:45:00Z&tf=30m&session=NSE"
    opens = [datetime.fromisoformat(b["ts_open"]) for b in c.get(f"/api/v1/footprint?{q}").json()["bars"]]
    assert opens[0] == datetime(2026, 1, 5, 3, 45, tzinfo=UTC) and all(o.minute in (15, 45) for o in opens)
    assert c.get(f"/api/v1/footprint?{q.replace('NSE', 'XYZ')}").status_code == 400


def test_ws_accepts_header_key_and_rejects_bad():
    import pytest
    from starlette.websockets import WebSocketDisconnect
    app = create_app(api_key="s3cret", rate_per_min=0)
    c = TestClient(app)
    with c.websocket_connect("/ws/v1/stream?topic=t", headers={"x-api-key": "s3cret"}) as ws:
        app.state.hub.publish("t", {"ok": 1})
        assert ws.receive_json()["ok"] == 1
    with pytest.raises(WebSocketDisconnect), c.websocket_connect("/ws/v1/stream?topic=t", headers={"x-api-key": "bad"}):
        pass
