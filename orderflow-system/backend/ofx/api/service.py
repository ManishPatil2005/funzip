"""Application service: provider data -> analytics -> JSON-safe dicts."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from ofx.domain import Trade, price_to_row
from ofx.orderflow import detectors
from ofx.orderflow import heatmap as hm
from ofx.orderflow import market_profile as mp
from ofx.orderflow import volume_profile as vp
from ofx.orderflow.footprint import (
    ImbalanceConfig,
    apply_session_cvd,
    build_footprint,
    find_imbalances,
    stacked_imbalances,
    utc_day,
)
from ofx.providers.base import MarketDataProvider

TF = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}
MAX_SPAN = timedelta(days=2)


class BadRequest(ValueError):
    pass


def parse_tf(tf: str) -> timedelta:
    if tf not in TF:
        raise BadRequest(f"timeframe must be one of {sorted(TF)}")
    return timedelta(seconds=TF[tf])


def check_span(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise BadRequest("start and end must include a UTC offset")
    if end <= start:
        raise BadRequest("end must be after start")
    if end - start > MAX_SPAN:
        raise BadRequest(f"span exceeds {MAX_SPAN}")


MAX_PAGE = 2000


def paginate(items: list[Any], key: str, limit: int | None, cursor: str | None) -> tuple[list[Any], str | None]:
    """Keyset pagination over a time-ordered list of dicts.

    The cursor is the `key` value (an ISO timestamp) of the first item of the next page, so pages stay stable when new
    data is appended and no offset arithmetic is involved. Compared as parsed datetimes, never as strings, because ISO
    strings with different UTC offsets do not sort lexically. limit=None returns everything (backwards compatible).
    """
    if limit is None and cursor is None:
        return items, None
    if limit is not None and not 1 <= limit <= MAX_PAGE:
        raise BadRequest(f"limit must be between 1 and {MAX_PAGE}")
    if cursor:
        try:
            c = datetime.fromisoformat(cursor)
        except ValueError as e:
            raise BadRequest("cursor is not a valid value returned by this API") from e
        if c.tzinfo is None:
            raise BadRequest("cursor is not a valid value returned by this API")
        items = [i for i in items if datetime.fromisoformat(i[key]) >= c]
    if limit is None or len(items) <= limit:
        return items, None
    return items[:limit], items[limit][key]


def bar_to_dict(b, cfg: ImbalanceConfig, min_stack: int) -> dict[str, Any]:
    imb = find_imbalances(b, cfg)
    return {
        "ts_open": b.ts_open.isoformat(), "ts_close": b.ts_close.isoformat(), "tick": b.tick,
        "open": b.open_px, "high": b.high_px, "low": b.low_px, "close": b.close_px,
        "volume": b.volume, "delta": b.delta, "delta_min": b.delta_min, "delta_max": b.delta_max,
        "cvd_open": b.cvd_open, "cvd_close": b.cvd_close, "poc_row": b.poc_row, "unknown_share": round(b.unknown_share, 4),
        "quality": b.quality.value,
        "rows": {str(r): [c.bid_vol, c.ask_vol] for r, c in sorted(b.rows.items())},
        "imbalances": [{"row": i.row, "side": i.side} for i in imb],
        "stacked": [asdict(s) for s in stacked_imbalances(imb, min_stack)],
    }


def _offset(spec: mp.SessionSpec | None, tf: str) -> timedelta:
    return mp.bar_align_offset(spec, parse_tf(tf)) if spec else timedelta(0)


def _skey(spec: mp.SessionSpec | None):  # type: ignore[no-untyped-def]
    """CVD resets per exchange session when a spec is given, else per UTC day."""
    if spec is None:
        return utc_day
    return lambda ts: spec.session_start(ts)


class Service:
    def __init__(self, provider: MarketDataProvider) -> None:
        self.p = provider

    async def _trades(self, iid: str, start: datetime, end: datetime) -> list[Trade]:
        if not self.p.capabilities.trades:
            raise BadRequest("provider has no trade data")
        return list(await self.p.trades(iid, start, end))

    async def footprint(self, iid: str, tick: float, start: datetime, end: datetime, tf: str, ratio: float = 3.0, min_stack: int = 3,
                        spec: mp.SessionSpec | None = None, limit: int | None = None, cursor: str | None = None) -> dict[str, Any]:
        check_span(start, end)
        bars = apply_session_cvd(build_footprint(await self._trades(iid, start, end), tick, parse_tf(tf), _offset(spec, tf)), _skey(spec))
        cfg = ImbalanceConfig(ratio=ratio)
        page, nxt = paginate([bar_to_dict(b, cfg, min_stack) for b in bars], "ts_open", limit, cursor)
        return {"provider": self.p.capabilities.name, "data_quality": self.p.capabilities.trade_quality.value,
                "bars": page, "total_bars": len(bars), "next_cursor": nxt}

    async def volume_profile(self, iid: str, tick: float, start: datetime, end: datetime) -> dict[str, Any]:
        check_span(start, end)
        prof = vp.from_trades(await self._trades(iid, start, end), tick)
        if not prof.volume:
            return {"empty": True}
        k = vp.key_levels(prof)
        return {"approximated": prof.approximated, "tick": tick, "rows": {str(r): v for r, v in sorted(prof.volume.items())},
                "levels": asdict(k), "nodes": [asdict(n) for n in vp.nodes(prof)]}

    async def observations(self, iid: str, tick: float, start: datetime, end: datetime, tf: str, spec: mp.SessionSpec | None = None,
                           limit: int | None = None, cursor: str | None = None) -> dict[str, Any]:
        check_span(start, end)
        bars = apply_session_cvd(build_footprint(await self._trades(iid, start, end), tick, parse_tf(tf), _offset(spec, tf)), _skey(spec))
        obs = [*detectors.delta_divergence(bars), *detectors.absorption(bars), *detectors.exhaustion(bars),
               *detectors.liquidity_sweep(bars, tick), *detectors.imbalance_clusters(bars)]
        t = detectors.cvd_trend(bars)
        if t:
            obs.append(t)
        rows = [o.to_dict() for o in sorted(obs, key=lambda o: o.ts_start)]
        page, nxt = paginate(rows, "ts_start", limit, cursor)
        return {"provider": self.p.capabilities.name, "observations": page, "total": len(rows), "next_cursor": nxt}

    async def market_profile(self, iid: str, tick: float, start: datetime, end: datetime, spec: mp.SessionSpec, period: int = 30) -> dict[str, Any]:
        check_span(start, end)
        candles = list(await self.p.candles(iid, start, end, "1m"))
        profs = mp.build_tpo(candles, spec, tick, period)
        out = []
        for p in profs:
            lv = mp.tpo_levels(p)
            out.append({"start": p.start.isoformat(), "counts": {str(r): n for r, n in sorted(p.counts.items())},
                        "letters": {str(r): s for r, s in sorted((p.letters or {}).items())}, "levels": asdict(lv)})
        return {"profiles": out, "note": "TPO is price-time based and independent of aggressor data."}

    async def heatmap(self, iid: str, tick: float, start: datetime, end: datetime, dt: float = 5.0,
                      scale: str = "log", mode: str = "max", max_cells: int = 200_000) -> dict[str, Any]:
        check_span(start, end)
        hist = getattr(self.p, "depth_history", None)
        if hist is None or self.p.capabilities.depth_levels == 0:
            raise BadRequest("provider has no depth history")
        if scale not in ("linear", "log", "percentile") or mode not in ("max", "avg"):
            raise BadRequest("scale must be linear|log|percentile and mode max|avg")
        if dt <= 0:
            raise BadRequest("dt must be positive")
        if end - start > timedelta(hours=6):
            raise BadRequest("heatmap span is limited to 6 hours")
        if (end - start).total_seconds() / dt > max_cells:
            raise BadRequest("heatmap too large; widen dt or shorten the span")  # rejected before any fetch
        snaps = list(await hist(iid, start, end))
        if not snaps:
            return {"empty": True}
        rows = [price_to_row(lv.price, tick) for s in snaps for lv in (*s.bids, *s.asks)]
        lo, hi = min(rows), max(rows)
        cols = int(np.ceil((end - start).total_seconds() / dt))
        if (hi - lo + 1) * cols > max_cells:
            raise BadRequest("heatmap too large; widen dt or shorten the span")
        h = hm.build_heatmap(snaps, tick, start, end, dt, lo, hi, mode)  # type: ignore[arg-type]
        inten = hm.intensity(h.matrix, scale)  # type: ignore[arg-type]
        return {"provider": self.p.capabilities.name, "depth_levels": self.p.capabilities.depth_levels,
                "t_start": start.isoformat(), "dt_seconds": dt, "row_lo": lo, "tick": tick, "scale": scale, "mode": mode,
                "shape": [int(inten.shape[0]), int(inten.shape[1])], "intensity": np.round(inten, 3).tolist(),
                "note": "Resting quantity is intent, not execution; coarse feeds give coarse maps."}

    async def scenarios(self, iid: str, tick: float, start: datetime, end: datetime, tf: str, spec: dict[str, Any]) -> dict[str, Any]:
        from ofx.strategy import SpecError, evaluate, parse_rule
        try:
            rule = parse_rule(spec)
        except SpecError as e:
            raise BadRequest(f"invalid rule: {e}") from e
        check_span(start, end)
        from ofx.replay import run_detectors
        bars, obs = run_detectors(await self._trades(iid, start, end), tick, parse_tf(tf))
        matches = evaluate(rule, obs, parse_tf(tf))
        return {"provider": self.p.capabilities.name, "rule": rule.name, "observations_considered": len(obs),
                "matches": [m.to_dict() for m in matches]}
