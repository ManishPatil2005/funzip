"""Run one or more strategies across a universe of instruments."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.data.provider import DataError, get_provider
from app.data.universe import Instrument
from app.strategies import builder
from app.strategies.builtin import NONE, REGISTRY, run_builtin

log = logging.getLogger("scanner.scan")


def _scan_one(inst: Instrument, interval: str, period: str, builtin_ids: list[str],
              overrides: dict, customs: list[builder.CustomStrategy]) -> dict:
    try:
        df = get_provider().history(inst, interval, period)
    except DataError as exc:
        return {"symbol": inst.symbol, "error": str(exc), "hits": []}
    except Exception:  # noqa: BLE001
        log.exception("unexpected data error for %s", inst.symbol)
        return {"symbol": inst.symbol, "error": "Data provider error", "hits": []}

    hits = []
    last = df.iloc[-1]
    for sid in builtin_ids:
        res = run_builtin(sid, df, overrides.get(sid))
        if res.signal != NONE:
            hits.append({"strategy": REGISTRY[sid].name, "id": sid, "signal": res.signal,
                         "reason": res.reason, "metrics": res.metrics})
    for cs in customs:
        res = builder.evaluate(df, cs)
        if res.signal != NONE:
            hits.append({"strategy": cs.name, "id": f"custom:{cs.name}", "signal": res.signal,
                         "reason": res.reason, "metrics": res.metrics})
    prev_close = df["close"].iloc[-2] if len(df) > 1 else last["close"]
    return {
        "symbol": inst.symbol, "exchange": inst.exchange, "proxy": inst.proxy,
        "price": round(float(last["close"]), 4),
        "change_pct": round(float(100 * (last["close"] - prev_close) / prev_close), 2) if prev_close else 0.0,
        "volume": float(last["volume"]),
        "as_of": df.index[-1].isoformat(),
        "hits": hits, "error": None,
    }


def scan(instruments: list[Instrument], interval: str, period: str, builtin_ids: list[str],
         overrides: dict | None = None, customs: list[builder.CustomStrategy] | None = None) -> list[dict]:
    settings = get_settings()
    overrides = overrides or {}
    customs = customs or []
    with ThreadPoolExecutor(max_workers=max(1, settings.scan_workers)) as pool:
        rows = list(pool.map(lambda i: _scan_one(i, interval, period, builtin_ids, overrides, customs), instruments))
    rows.sort(key=lambda r: (-len(r["hits"]), r["symbol"]))
    return rows
