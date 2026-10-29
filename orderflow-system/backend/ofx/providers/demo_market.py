"""Deterministic demo markets that look like real index/commodity futures sessions.

NOT market data. Purpose: let the UI, detectors and exports be exercised with realistic scale and shape
(NIFTY-like price level and tick, session-shaped volume, delta that follows price) without credentials or a live feed.
Everything is labelled provider "synthetic"; the UI shows a DEMO badge for it.

Model (per weekday, seeded by instrument and date, so any query window returns the same trades):
  * latent order-flow state m_t (AR(1)) drives both the aggressor mix and a small drift of the fair price,
    so delta correlates with price direction the way real flow does;
  * fair price F_t is a random walk at 1-second resolution, volatility scaled by intraday activity;
  * trade price = F_t + bid/ask bounce + micro noise, rounded to the tick grid;
  * trade arrival is Poisson with a U-shaped intensity (busy open and close);
  * trade size is log-normal with rare block prints.
Calibration targets (documented, not claimed to match any real day): NIFTY ~ 22,600 / tick 0.05 / ~35k lots per 5 min;
crude oil ~ 8,900 / tick 1 / ~600 lots per 5 min.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import numpy as np

from ofx.domain import AggressorSide, DepthLevel, DepthSnapshot, Instrument, Trade


@dataclass(frozen=True)
class DemoSpec:
    instrument: Instrument
    open_local: time
    minutes: int
    base_px: float
    day_vol_pct: float  # target std of the day's move, percent of price
    trades_per_sec: float
    median_qty: float
    depth_step: float  # price distance between synthetic depth levels
    wall_every: float  # resting "walls" sit on multiples of this price step


NIFTY = DemoSpec(Instrument("SYN:NIFTY", "NIFTY-I", "NSE", 0.05, 75.0, "Asia/Kolkata"), time(9, 15), 375, 22600.0, 0.45, 1.5, 40.0, 1.0, 50.0)
CRUDE = DemoSpec(Instrument("SYN:CRUDE", "CRUDEOIL-I", "MCX", 1.0, 100.0, "Asia/Kolkata"), time(9, 0), 870, 8900.0, 0.8, 0.5, 2.0, 5.0, 50.0)
SPECS: dict[str, DemoSpec] = {s.instrument.iid: s for s in (NIFTY, CRUDE)}
ROW_HINT: dict[str, float] = {"SYN:NIFTY": 2.5, "SYN:CRUDE": 5.0}  # sensible first row size for the UI (it then adapts to zoom)


def is_demo(iid: str) -> bool:
    return iid in SPECS


def _seed(iid: str, day: date) -> int:
    return (sum(ord(c) * (i + 1) for i, c in enumerate(iid)) * 100003 + day.toordinal()) % (2**32)


def session_start_utc(spec: DemoSpec, day: date) -> datetime:
    zone = ZoneInfo(spec.instrument.tz)
    return datetime.combine(day, spec.open_local, tzinfo=zone).astimezone(UTC)


def trading_days(spec: DemoSpec, start: datetime, end: datetime) -> list[date]:
    zone = ZoneInfo(spec.instrument.tz)
    d0, d1 = start.astimezone(zone).date() - timedelta(days=1), end.astimezone(zone).date()
    return [d0 + timedelta(days=i) for i in range((d1 - d0).days + 1) if (d0 + timedelta(days=i)).weekday() < 5]


@lru_cache(maxsize=24)
def _day(iid: str, day: date) -> tuple[tuple[Trade, ...], tuple[float, ...]]:
    """(trades, per-second last price) for one session."""
    spec = SPECS[iid]
    tick = spec.instrument.tick_size
    rng = np.random.default_rng(_seed(iid, day))
    secs = spec.minutes * 60
    t = np.arange(secs)
    # U-shaped activity: busy in the first and last 45 minutes
    act = 1.0 + 1.6 * np.exp(-t / 1800.0) + 1.2 * np.exp(-(secs - t) / 1800.0)
    act /= act.mean()
    # latent order-flow state, AR(1)
    m = np.zeros(secs)
    eps = rng.normal(0.0, 0.22, secs)
    for i in range(1, secs):
        m[i] = 0.97 * m[i - 1] + eps[i]
    sigma_s = spec.base_px * spec.day_vol_pct / 100.0 / np.sqrt(secs)
    gap = spec.base_px * 0.003 * np.sin(day.toordinal() / 3.3) + rng.normal(0.0, spec.base_px * 0.0015)
    steps = sigma_s * np.sqrt(act) * rng.normal(0.0, 1.0, secs) + sigma_s * 0.10 * np.tanh(m)
    fair = spec.base_px + gap + np.cumsum(steps)
    fair = np.maximum(fair, tick * 10)

    counts = rng.poisson(spec.trades_per_sec * act)
    n = int(counts.sum())
    sec_idx = np.repeat(t, counts)
    ms = rng.integers(0, 1000, n)
    order = np.lexsort((ms, sec_idx))
    sec_idx, ms = sec_idx[order], ms[order]
    p_ask = 1.0 / (1.0 + np.exp(-1.3 * m[sec_idx]))
    is_ask = rng.random(n) < p_ask
    bounce = np.where(is_ask, 1.0, -1.0) * rng.integers(0, 3, n) * tick
    noise = rng.normal(0.0, 2.0 * tick, n)
    px = np.round((fair[sec_idx] + bounce + noise) / tick) * tick
    px = np.maximum(px, tick)
    qty = np.maximum(1.0, np.round(rng.lognormal(np.log(spec.median_qty), 0.95, n)))
    block = rng.random(n) < 0.01
    qty = np.where(block, qty * rng.integers(6, 15, n), qty)

    start = session_start_utc(spec, day)
    trades = tuple(
        Trade(start + timedelta(seconds=int(sec_idx[i]), milliseconds=int(ms[i])), round(float(px[i]), 6), float(qty[i]),
              AggressorSide.ASK if is_ask[i] else AggressorSide.BID, i + 1, "exchange")
        for i in range(n))
    last = np.full(secs, np.nan)
    last[sec_idx] = px  # later trades in the same second overwrite earlier ones
    series = np.where(np.isnan(last), fair, last)
    return trades, tuple(float(x) for x in series)


def trades_between(iid: str, start: datetime, end: datetime) -> list[Trade]:
    spec = SPECS[iid]
    out: list[Trade] = []
    for d in trading_days(spec, start, end):
        tr = _day(iid, d)[0]
        keys = [x.ts for x in tr]
        out.extend(tr[bisect.bisect_left(keys, start):bisect.bisect_left(keys, end)])
    return out


def depth_between(iid: str, start: datetime, end: datetime, levels: int = 20) -> list[DepthSnapshot]:
    """One snapshot per second. Resting size is thicker near round-number 'wall' prices and thins away from the touch."""
    spec = SPECS[iid]
    tick, step = spec.instrument.tick_size, spec.depth_step
    out: list[DepthSnapshot] = []
    for d in trading_days(spec, start, end):
        s0 = session_start_utc(spec, d)
        series = _day(iid, d)[1]
        rng = np.random.default_rng(_seed(iid, d) + 1)
        k0 = max(0, int((start - s0).total_seconds()))
        k1 = min(len(series), int((end - s0).total_seconds()))
        for k in range(k0, k1):
            mid = round(series[k] / tick) * tick
            bids: list[DepthLevel] = []
            asks: list[DepthLevel] = []
            for i in range(1, levels + 1):
                for sign, book in ((-1, bids), (1, asks)):
                    price = round(mid + sign * i * step, 6)
                    near_wall = abs(price / spec.wall_every - round(price / spec.wall_every)) * spec.wall_every < step / 2
                    size = (spec.median_qty * 8) * (1.4 - i / (levels * 1.2)) * float(rng.uniform(0.6, 1.4))
                    if near_wall:
                        size *= 6.0
                    book.append(DepthLevel(price, max(1.0, round(size))))
            out.append(DepthSnapshot(s0 + timedelta(seconds=k), tuple(bids), tuple(asks), k))
    return out
