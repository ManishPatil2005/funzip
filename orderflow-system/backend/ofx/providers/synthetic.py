"""Deterministic synthetic market: for tests, demos and offline development.

Not a market model. It produces plausible-looking trades and depth so the pipeline can
be exercised without credentials. Output is always labelled with provider name 'synthetic'.
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime, timedelta

from ofx.domain import AggressorSide, Candle, DepthLevel, DepthSnapshot, Instrument, Quote, Trade
from ofx.providers import demo_market as dm
from ofx.providers.base import Capabilities, ProviderUnsupported

INSTRUMENT = Instrument("SYN:TEST", "TEST", "SYN", tick_size=0.5, lot_size=1.0, tz="UTC")


def generate_trades(start: datetime, seconds: int, seed: int = 7, start_px: float = 100.0, tick: float = 0.5,
                    with_side: bool = True) -> list[Trade]:
    rng = random.Random(seed)
    px, out, seq = start_px, [], 0
    for s in range(seconds):
        for _ in range(rng.randint(1, 4)):
            px = max(tick, px + rng.choice((-1, 0, 0, 1)) * tick)
            side = AggressorSide.ASK if rng.random() < 0.5 else AggressorSide.BID
            seq += 1
            out.append(Trade(
                start + timedelta(seconds=s, milliseconds=rng.randint(0, 900)), round(px, 6), float(rng.randint(1, 20)),
                side if with_side else AggressorSide.UNKNOWN, seq, "exchange" if with_side else "none"))
    return sorted(out, key=lambda t: (t.ts, t.seq))


def generate_depth(ts: datetime, mid: float, tick: float = 0.5, levels: int = 10, seed: int = 1, seq: int = 0) -> DepthSnapshot:
    rng = random.Random(seed)
    bids = tuple(DepthLevel(round(mid - tick * (i + 1), 6), float(rng.randint(5, 50))) for i in range(levels))
    asks = tuple(DepthLevel(round(mid + tick * (i + 1), 6), float(rng.randint(5, 50))) for i in range(levels))
    return DepthSnapshot(ts, bids, asks, seq)


class SyntheticProvider:
    capabilities = Capabilities(
        name="synthetic", trades=True, aggressor_flag=True, depth_levels=10, historical_trades=True,
        historical_candles=True, notes="Generated data. Not a market.")

    def __init__(self, tick_delay: float = 0.0) -> None:
        self._delay = tick_delay

    async def instruments(self) -> Sequence[Instrument]:
        return [INSTRUMENT, *(s.instrument for s in dm.SPECS.values())]

    async def trades(self, iid: str, start: datetime, end: datetime) -> Sequence[Trade]:
        if dm.is_demo(iid):
            return dm.trades_between(iid, start, end)
        return generate_trades(start, int((end - start).total_seconds()))

    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Candle]:
        step = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600}.get(timeframe if dm.is_demo(iid) else timeframe) if dm.is_demo(iid) \
            else {"1m": 60, "5m": 300}.get(timeframe)
        if step is None:
            raise ProviderUnsupported(f"timeframe {timeframe}")
        trades = dm.trades_between(iid, start, end) if dm.is_demo(iid) else generate_trades(start, int((end - start).total_seconds()))
        buckets: dict[int, list[Trade]] = {}
        for t in trades:
            buckets.setdefault(int(t.ts.timestamp()) // step, []).append(t)
        return [Candle(datetime.fromtimestamp(k * step, tz=UTC), v[0].price, max(t.price for t in v),
                       min(t.price for t in v), v[-1].price, sum(t.qty for t in v)) for k, v in sorted(buckets.items())]

    async def depth_history(self, iid: str, start: datetime, end: datetime) -> list[DepthSnapshot]:
        """One snapshot per second around a slowly drifting mid, with an occasional wall."""
        if dm.is_demo(iid):
            return dm.depth_between(iid, start, end)
        rng = random.Random(11)
        mid, out = 100.0, []
        for k in range(int((end - start).total_seconds())):
            mid = max(1.0, mid + rng.choice((-0.5, 0.0, 0.0, 0.5)))
            snap = generate_depth(start + timedelta(seconds=k), mid, seed=k, seq=k)
            if k % 17 < 6:  # a wall that persists ~6 s every 17 s
                bids = (DepthLevel(snap.bids[3].price, 400.0), *[b for i, b in enumerate(snap.bids) if i != 3])
                snap = DepthSnapshot(snap.ts, tuple(sorted(bids, key=lambda l: -l.price)), snap.asks, snap.seq)
            out.append(snap)
        return out

    async def stream_trades(self, iid: str) -> AsyncIterator[Trade]:
        now = datetime.now(UTC)
        for t in generate_trades(now, 300, seed=int(now.timestamp()) % 1000):
            yield Trade(datetime.now(UTC), t.price, t.qty, t.side, t.seq, t.side_method)
            await asyncio.sleep(self._delay)

    async def stream_depth(self, iid: str) -> AsyncIterator[DepthSnapshot]:
        seq = 0
        while True:
            seq += 1
            yield generate_depth(datetime.now(UTC), 100.0, seed=seq, seq=seq)
            await asyncio.sleep(max(self._delay, 0.01))

    async def stream_quotes(self, iid: str) -> AsyncIterator[Quote]:
        while True:
            yield Quote(datetime.now(UTC), 99.5, 100.5, 10, 10)
            await asyncio.sleep(max(self._delay, 0.01))
