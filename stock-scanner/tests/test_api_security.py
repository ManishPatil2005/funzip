import pytest

from app.core.config import Settings
from app.strategies import builder

KEY = {"X-API-Key": "k" * 40}


def test_pages_and_security_headers(client):
    for path in ("/", "/builder", "/profile"):
        r = client.get(path)
        assert r.status_code == 200
        assert "script-src 'self'" in r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "<script>" not in r.text.replace("<script src=", "")  # no inline scripts (CSP)
        assert " style=" not in r.text


def test_api_requires_key_when_configured(secure_client):
    assert secure_client.get("/api/meta").status_code == 401
    assert secure_client.get("/api/meta", headers={"X-API-Key": "wrong" * 10}).status_code == 401
    assert secure_client.get("/api/meta", headers=KEY).status_code == 200
    assert secure_client.get("/healthz").status_code == 200
    assert secure_client.get("/api/meta", headers=KEY).headers["cache-control"] == "no-store"


def test_production_requires_strong_keys_and_blocks_synthetic(monkeypatch):
    with pytest.raises(RuntimeError):
        Settings(env="production", api_keys=()).validate()
    with pytest.raises(RuntimeError):
        Settings(env="production", api_keys=("short",)).validate()
    with pytest.raises(RuntimeError):
        Settings(env="production", api_keys=("k" * 40,), allowed_hosts=("*",)).validate()
    with pytest.raises(RuntimeError):
        Settings(env="production", api_keys=("k" * 40,), data_provider="synthetic").validate()
    Settings(env="production", api_keys=("k" * 40,)).validate()


def test_scan_rate_limit(secure_client):
    body = {"symbols": ["TCS"], "strategies": ["ema_cross"]}
    codes = [secure_client.post("/api/scan", json=body, headers=KEY).status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429
    assert secure_client.post("/api/scan", json=body, headers=KEY).headers["retry-after"]


def test_body_size_limit(client):
    big = {"name": "x" * 70_000}
    assert client.post("/api/custom/validate", json=big).status_code == 413


def test_x_forwarded_for_cannot_bypass_rate_limit_by_default(secure_client):
    body = {"symbols": ["TCS"], "strategies": ["ema_cross"]}
    codes = [secure_client.post("/api/scan", json=body, headers={**KEY, "X-Forwarded-For": f"1.2.3.{i}"}).status_code
             for i in range(5)]
    assert 429 in codes


def test_scan_validation(client):
    ok = {"symbols": ["TCS", "NSE:IRCTC"], "strategies": ["ema_cross"], "interval": "1d", "period": "1y"}
    assert client.post("/api/scan", json=ok).status_code == 200
    bad = [
        {**ok, "interval": "2m"}, {**ok, "interval": "15m", "period": "1y"}, {**ok, "symbols": ["TCS; DROP TABLE"]},
        {**ok, "symbols": ["NOTREAL"]}, {**ok, "strategies": ["nope"]}, {**ok, "strategies": []},
        {**ok, "params": {"ema_cross": {"fast": -1}}}, {**ok, "universe": "WORLD", "symbols": None},
        {**ok, "unexpected": 1}, {**ok, "signal": "HOLD"}, {**ok, "symbols": ["TCS"] * 101},
    ]
    for payload in bad:
        assert client.post("/api/scan", json=payload).status_code in (404, 422), payload


def test_scan_universe_and_signal_filter(client):
    r = client.post("/api/scan", json={"universe": "MCX", "interval": "1d", "period": "1y",
                                       "strategies": ["donchian", "rsi_reversal", "nr7", "candle_engulfing"]})
    j = r.json()
    assert r.status_code == 200 and j["scanned"] == 7 and all(x["proxy"] for x in j["results"])
    r = client.post("/api/scan", json={"universe": "NIFTY50", "interval": "1d", "period": "1y",
                                       "strategies": ["donchian", "nr7"], "signal": "BUY"})
    assert all(any(h["signal"] == "BUY" for h in x["hits"]) for x in r.json()["results"])


def test_provider_failures_are_reported_per_symbol(client, monkeypatch):
    from app.data import provider

    class Broken(provider.DataProvider):
        def history(self, inst, interval, period):
            raise provider.DataError("upstream down")

    provider.set_provider(Broken())
    r = client.post("/api/scan", json={"symbols": ["TCS"], "strategies": ["ema_cross"]})
    assert r.status_code == 200 and r.json()["results"][0]["error"] == "upstream down"
    assert client.get("/api/profile/TCS").status_code == 502


def test_custom_strategy_crud_and_scan(client):
    t = builder.TEMPLATES[0]
    assert client.post("/api/custom", json=t).status_code == 201
    assert client.post("/api/custom", json=t).status_code == 201  # upsert
    assert [s["name"] for s in client.get("/api/custom").json()] == [t["name"]]
    r = client.post("/api/scan", json={"symbols": ["TCS", "INFY"], "custom": [t["name"]]})
    assert r.status_code == 200
    assert client.post("/api/scan", json={"symbols": ["TCS"], "custom": ["missing"]}).status_code == 404
    assert client.post("/api/custom/test?symbol=TCS", json=t).status_code == 200
    assert client.delete("/api/custom/" + t["name"]).status_code == 200
    assert client.delete("/api/custom/" + t["name"]).status_code == 404


def test_custom_strategy_rejects_bad_payloads(client):
    evil = {"name": "x", "buy": {"all": [{"left": {"ind": "__import__('os').system('id')"}, "op": ">", "right": {"value": 1}}]}}
    assert client.post("/api/custom", json=evil).status_code == 422
    assert client.post("/api/custom", json={"name": "'; DROP TABLE custom_strategies;--", "buy": builder.TEMPLATES[0]["buy"]}).status_code == 422
    assert client.get("/api/custom").status_code == 200  # table intact


def test_sql_injection_in_name_path_is_inert(client):
    assert client.delete("/api/custom/' OR '1'='1").status_code == 404


def test_profile_endpoint_and_validation(client):
    r = client.get("/api/profile/NIFTY50")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"]["rows"] and body["bias"]["signal"] in ("BUY", "SELL", "NEUTRAL")
    assert client.get("/api/profile/GOLD?interval=15m&period=5d").status_code == 200
    assert client.get("/api/profile/TCS?interval=1d").status_code == 422
    assert client.get("/api/profile/TCS?date=notadate").status_code == 422
    assert client.get("/api/profile/TCS?date=1999-01-01").status_code == 422
    assert client.get("/api/profile/UNKNOWNSYM").status_code == 404
    assert client.get("/api/profile/TCS/ascii").json()["text"].startswith("20")


def test_docs_hidden_in_production(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core import config
    from app.main import create_app

    monkeypatch.setenv("SCANNER_ENV", "production")
    monkeypatch.setenv("SCANNER_API_KEYS", "k" * 40)
    monkeypatch.setenv("SCANNER_DATA_PROVIDER", "yfinance")
    monkeypatch.setenv("SCANNER_ALLOWED_HOSTS", "testserver")
    monkeypatch.setenv("SCANNER_DATABASE_PATH", str(tmp_path / "p.db"))
    config.get_settings.cache_clear()
    with TestClient(create_app()) as c:
        assert c.get("/docs").status_code == 404
        assert c.get("/openapi.json").status_code == 404
        assert c.get("/", headers={"host": "evil.example"}).status_code == 400  # TrustedHost
    config.get_settings.cache_clear()
