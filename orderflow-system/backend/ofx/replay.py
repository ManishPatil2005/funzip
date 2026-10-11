"""Replay: run the detectors over recorded trades, one session/day at a time.

Purpose is review, not prediction: it shows how often each observation kind fires on YOUR recorded data
and how confident it is, so thresholds can be tuned deliberately instead of trusted blindly.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Sequence
from datetime import datetime, timedelta
from typing import Any

from ofx.domain import Trade
from ofx.orderflow import detectors
from ofx.orderflow.footprint import apply_session_cvd, build_footprint, utc_day
from ofx.orderflow.observation import Observation


def run_detectors(trades: Sequence[Trade], tick: float, timeframe: timedelta,
                  session_key: Callable[[datetime], Hashable] = utc_day) -> tuple[list[Any], list[Observation]]:
    bars = apply_session_cvd(build_footprint(trades, tick, timeframe), session_key)
    obs = [*detectors.delta_divergence(bars), *detectors.absorption(bars), *detectors.exhaustion(bars),
           *detectors.liquidity_sweep(bars, tick), *detectors.imbalance_clusters(bars)]
    t = detectors.cvd_trend(bars)
    if t:
        obs.append(t)
    return bars, sorted(obs, key=lambda o: o.ts_start)


def replay_by_day(trades: Sequence[Trade], tick: float, timeframe: timedelta,
                  session_key: Callable[[datetime], Hashable] = utc_day) -> dict[str, dict[str, Any]]:
    """Per-day summary: bars, trades, observation counts per kind, mean confidence, quality mix."""
    days: dict[str, list[Trade]] = defaultdict(list)
    for t in trades:
        days[str(session_key(t.ts))].append(t)
    out: dict[str, dict[str, Any]] = {}
    for day, ts in sorted(days.items()):
        bars, obs = run_detectors(ts, tick, timeframe, session_key)
        kinds = Counter(o.kind for o in obs)
        out[day] = {
            "trades": len(ts), "bars": len(bars), "observations": len(obs), "by_kind": dict(sorted(kinds.items())),
            "mean_confidence": round(sum(o.confidence for o in obs) / len(obs), 3) if obs else None,
            "quality": dict(Counter(o.data_quality.value for o in obs)),
        }
    return out
