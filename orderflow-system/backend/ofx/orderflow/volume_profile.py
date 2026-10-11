"""Volume profile: histogram, POC, value area, HVN/LVN, composites."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from ofx.domain import Candle, Trade, price_to_row, row_to_price
from ofx.orderflow.common import (
    local_extrema,
    moving_average,
    poc_index,
    prominence,
    value_area_indices,
)


@dataclass
class VolumeProfile:
    tick: float
    volume: dict[int, float] = field(default_factory=dict)
    ask: dict[int, float] = field(default_factory=dict)
    bid: dict[int, float] = field(default_factory=dict)
    approximated: bool = False  # True when built from bars rather than trades

    def add(self, row: int, vol: float, ask: float = 0.0, bid: float = 0.0) -> None:
        self.volume[row] = self.volume.get(row, 0.0) + vol
        if ask:
            self.ask[row] = self.ask.get(row, 0.0) + ask
        if bid:
            self.bid[row] = self.bid.get(row, 0.0) + bid

    @property
    def total(self) -> float:
        return sum(self.volume.values())

    def dense(self) -> tuple[int, list[float]]:
        """(first_row, contiguous volumes with zeros for gaps)."""
        if not self.volume:
            raise ValueError("empty profile")
        lo, hi = min(self.volume), max(self.volume)
        return lo, [self.volume.get(r, 0.0) for r in range(lo, hi + 1)]


def from_trades(trades: Iterable[Trade], tick: float) -> VolumeProfile:
    vp = VolumeProfile(tick)
    for t in trades:
        r = price_to_row(t.price, tick)
        vp.add(r, t.qty, ask=t.qty if t.side.value == "ask" else 0.0, bid=t.qty if t.side.value == "bid" else 0.0)
    return vp


def from_candles(
    candles: Iterable[Candle], tick: float, distribution: Literal["uniform", "close_weighted"] = "uniform"
) -> VolumeProfile:
    """Approximate profile from OHLCV. Volume is spread over each bar's price rows.

    This cannot know where volume truly traded inside the bar; the result is
    flagged `approximated` and every consumer must show that.
    """
    vp = VolumeProfile(tick, approximated=True)
    for c in candles:
        lo, hi = price_to_row(c.low, tick), price_to_row(c.high, tick)
        n = hi - lo + 1
        if distribution == "close_weighted" and n > 1:
            close_row = price_to_row(c.close, tick)
            weights = [1.0 / (1 + abs(r - close_row)) for r in range(lo, hi + 1)]
        else:
            weights = [1.0] * n
        s = sum(weights)
        for r, w in zip(range(lo, hi + 1), weights):
            vp.add(r, c.volume * w / s)
    return vp


def merge(profiles: Sequence[VolumeProfile]) -> VolumeProfile:
    """Composite profile across sessions (all must share the tick size)."""
    if not profiles:
        raise ValueError("nothing to merge")
    tick = profiles[0].tick
    out = VolumeProfile(tick, approximated=any(p.approximated for p in profiles))
    for p in profiles:
        if abs(p.tick - tick) > 1e-12:
            raise ValueError("cannot merge profiles with different tick sizes")
        for r, v in p.volume.items():
            out.add(r, v, p.ask.get(r, 0.0), p.bid.get(r, 0.0))
    return out


@dataclass(frozen=True)
class KeyLevels:
    poc: float
    vah: float
    val: float
    poc_row: int
    vah_row: int
    val_row: int
    value_area_volume_share: float


def key_levels(vp: VolumeProfile, pct: float = 0.70) -> KeyLevels:
    """POC and the value area. VAH/VAL are the prices of the top/bottom value-area rows."""
    first, dense = vp.dense()
    p = poc_index(dense)
    lo, hi = value_area_indices(dense, p, pct)
    total = sum(dense)
    return KeyLevels(
        poc=row_to_price(first + p, vp.tick), vah=row_to_price(first + hi, vp.tick),
        val=row_to_price(first + lo, vp.tick), poc_row=first + p, vah_row=first + hi, val_row=first + lo,
        value_area_volume_share=sum(dense[lo:hi + 1]) / total if total else 0.0,
    )


@dataclass(frozen=True)
class Node:
    kind: Literal["HVN", "LVN"]
    row: int
    price: float
    volume: float
    prominence_share: float  # prominence as a share of the profile peak (smoothed)


def nodes(vp: VolumeProfile, smooth: int = 3, prominence_share: float = 0.15) -> list[Node]:
    """High and low volume nodes.

    The histogram is smoothed (centred moving average, odd window) to suppress
    row-level noise. HVN = local maximum of the smoothed series whose prominence
    is at least `prominence_share` of the peak; LVN = local minimum (not at the
    profile edges) with depth at least `prominence_share` of the peak.
    """
    if smooth % 2 == 0:
        raise ValueError("smooth window must be odd")
    first, dense = vp.dense()
    s = moving_average(dense, smooth)
    peak = max(s)
    if peak <= 0:
        return []
    out: list[Node] = []
    for i in local_extrema(s, "max"):
        prom = prominence(s, i, "max") / peak
        if prom >= prominence_share:
            out.append(Node("HVN", first + i, row_to_price(first + i, vp.tick), dense[i], prom))
    n = len(s)
    for i in local_extrema(s, "min"):
        if i in (0, n - 1):
            continue
        prom = prominence(s, i, "min") / peak
        if prom >= prominence_share:
            out.append(Node("LVN", first + i, row_to_price(first + i, vp.tick), dense[i], prom))
    return sorted(out, key=lambda x: x.row)
