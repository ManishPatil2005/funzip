"""Footprint (cluster) bars: bid/ask volume per price row, delta, CVD, imbalances.

Rows are integer indices (price / tick). Volume whose aggressor side is unknown
is kept apart (`unknown_vol`) and never assigned to a side.
"""
from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from ofx.domain import AggressorSide, DataQuality, Trade, price_to_row
from ofx.orderflow.common import poc_index, value_area_indices


@dataclass(slots=True)
class Cell:
    bid_vol: float = 0.0  # volume where the seller was the aggressor (hit the bid)
    ask_vol: float = 0.0  # volume where the buyer was the aggressor (lifted the offer)
    unknown_vol: float = 0.0
    bid_trades: int = 0
    ask_trades: int = 0

    @property
    def volume(self) -> float:
        return self.bid_vol + self.ask_vol + self.unknown_vol

    @property
    def delta(self) -> float:
        return self.ask_vol - self.bid_vol


@dataclass
class FootprintBar:
    ts_open: datetime
    ts_close: datetime
    tick: float
    open_px: float
    high_px: float
    low_px: float
    close_px: float
    rows: dict[int, Cell] = field(default_factory=dict)
    n_trades: int = 0
    quality: DataQuality = DataQuality.EXACT
    delta_min: float = 0.0  # lowest running delta inside the bar (starts at 0)
    delta_max: float = 0.0
    cvd_open: float = 0.0
    cvd_close: float = 0.0

    @property
    def volume(self) -> float:
        return sum(c.volume for c in self.rows.values())

    @property
    def ask_volume(self) -> float:
        return sum(c.ask_vol for c in self.rows.values())

    @property
    def bid_volume(self) -> float:
        return sum(c.bid_vol for c in self.rows.values())

    @property
    def unknown_volume(self) -> float:
        return sum(c.unknown_vol for c in self.rows.values())

    @property
    def unknown_share(self) -> float:
        v = self.volume
        return self.unknown_volume / v if v else 0.0

    @property
    def delta(self) -> float:
        return self.ask_volume - self.bid_volume

    @property
    def low_row(self) -> int:
        return min(self.rows)

    @property
    def high_row(self) -> int:
        return max(self.rows)

    @property
    def range_ticks(self) -> int:
        return self.high_row - self.low_row + 1

    @property
    def poc_row(self) -> int:
        rows = sorted(self.rows)
        dense = [self.rows[r].volume if r in self.rows else 0.0 for r in range(rows[0], rows[-1] + 1)]
        return rows[0] + poc_index(dense)

    def value_area(self, pct: float = 0.70) -> tuple[int, int]:
        rows = sorted(self.rows)
        lo = rows[0]
        dense = [self.rows[r].volume if r in self.rows else 0.0 for r in range(lo, rows[-1] + 1)]
        a, b = value_area_indices(dense, poc_index(dense), pct)
        return lo + a, lo + b


def _floor_ts(ts: datetime, secs: int, offset: int) -> datetime:
    epoch = int(ts.timestamp())
    start = ((epoch - offset) // secs) * secs + offset
    return datetime.fromtimestamp(start, tz=UTC)


def build_footprint(
    trades: Iterable[Trade],
    tick: float,
    timeframe: timedelta,
    align_offset: timedelta = timedelta(0),
) -> list[FootprintBar]:
    """Aggregate trades into time-based footprint bars.

    align_offset shifts bar boundaries (for example 03:45 UTC so 30-minute bars
    start at 09:15 IST). Bars with no trades are omitted.
    """
    if tick <= 0:
        raise ValueError("tick must be positive")
    secs = int(timeframe.total_seconds())
    if secs <= 0:
        raise ValueError("timeframe must be positive")
    offset = int(align_offset.total_seconds()) % secs
    bars: dict[datetime, FootprintBar] = {}
    running: dict[datetime, float] = {}
    exact_flags: dict[datetime, bool] = {}

    for t in sorted(trades, key=lambda x: (x.ts, x.seq)):
        start = _floor_ts(t.ts, secs, offset)
        bar = bars.get(start)
        if bar is None:
            bar = FootprintBar(start, start + timeframe, tick, t.price, t.price, t.price, t.price)
            bars[start] = bar
            running[start] = 0.0
            exact_flags[start] = True
        row = price_to_row(t.price, tick)
        cell = bar.rows.setdefault(row, Cell())
        if t.side is AggressorSide.ASK:
            cell.ask_vol += t.qty
            cell.ask_trades += 1
            running[start] += t.qty
        elif t.side is AggressorSide.BID:
            cell.bid_vol += t.qty
            cell.bid_trades += 1
            running[start] -= t.qty
        else:
            cell.unknown_vol += t.qty
        if t.side is AggressorSide.UNKNOWN or t.side_method != "exchange":
            exact_flags[start] = False
        bar.n_trades += 1
        bar.high_px, bar.low_px, bar.close_px = max(bar.high_px, t.price), min(bar.low_px, t.price), t.price
        bar.delta_min = min(bar.delta_min, running[start])
        bar.delta_max = max(bar.delta_max, running[start])

    out = [bars[k] for k in sorted(bars)]
    for b in out:
        b.quality = DataQuality.EXACT if exact_flags[b.ts_open] else DataQuality.ESTIMATED
    return out


SessionKey = Callable[[datetime], Hashable]


def utc_day(ts: datetime) -> date:
    return ts.astimezone(UTC).date()


def apply_session_cvd(bars: list[FootprintBar], session_key: SessionKey = utc_day) -> list[FootprintBar]:
    """Set cvd_open/cvd_close on each bar; the running total resets when the session changes."""
    current: Hashable | None = None
    cvd = 0.0
    for b in bars:
        key = session_key(b.ts_open)
        if key != current:
            current, cvd = key, 0.0
        b.cvd_open = cvd
        cvd += b.delta
        b.cvd_close = cvd
    return bars


# ----------------------------------------------------------------------- imbalance
@dataclass(frozen=True)
class ImbalanceConfig:
    ratio: float = 3.0  # dominant side must be at least ratio x the diagonal opposing side
    min_volume: float = 0.0  # dominant-side floor, avoids spurious ratios on tiny volumes
    min_diff: float = 0.0  # dominant minus opposing floor
    ignore_zero: bool = False  # True: an opposing zero never counts as an imbalance


@dataclass(frozen=True)
class Imbalance:
    row: int
    side: Literal["ask", "bid"]
    own: float
    opposing: float

    @property
    def ratio(self) -> float:
        return float("inf") if self.opposing == 0 else self.own / self.opposing


def find_imbalances(bar: FootprintBar, cfg: ImbalanceConfig = ImbalanceConfig()) -> list[Imbalance]:
    """Diagonal imbalances.

    Ask imbalance at row r: ask[r] vs bid[r-1] (buyers lifting above resting sellers one row below).
    Bid imbalance at row r: bid[r] vs ask[r+1] (sellers hitting below resting buyers one row above).
    Rows outside the bar's traded range have no opposing cell and are skipped (their
    zero is structural, not informational). Holes inside the range count as zero.
    """
    lo, hi = bar.low_row, bar.high_row
    out: list[Imbalance] = []

    def passes(own: float, opp: float) -> bool:
        if own <= 0 or own < cfg.min_volume or own - opp < cfg.min_diff:
            return False
        if opp == 0:
            return not cfg.ignore_zero
        return own >= cfg.ratio * opp

    for r in range(lo, hi + 1):
        cell = bar.rows.get(r)
        if cell is None:
            continue
        if r - 1 >= lo:
            opp = bar.rows[r - 1].bid_vol if r - 1 in bar.rows else 0.0
            if passes(cell.ask_vol, opp):
                out.append(Imbalance(r, "ask", cell.ask_vol, opp))
        if r + 1 <= hi:
            opp = bar.rows[r + 1].ask_vol if r + 1 in bar.rows else 0.0
            if passes(cell.bid_vol, opp):
                out.append(Imbalance(r, "bid", cell.bid_vol, opp))
    return out


@dataclass(frozen=True)
class StackedImbalance:
    side: Literal["ask", "bid"]
    low_row: int
    high_row: int

    @property
    def n_rows(self) -> int:
        return self.high_row - self.low_row + 1


def stacked_imbalances(imbalances: list[Imbalance], min_rows: int = 3) -> list[StackedImbalance]:
    """Runs of >= min_rows consecutive rows flagged on the same side."""
    out: list[StackedImbalance] = []
    for side in ("ask", "bid"):
        rows = sorted(i.row for i in imbalances if i.side == side)
        start = prev = None
        for r in rows + [None]:  # type: ignore[list-item]
            if start is None:
                start = prev = r
                continue
            if r is not None and prev is not None and r == prev + 1:
                prev = r
                continue
            if prev is not None and start is not None and prev - start + 1 >= min_rows:
                out.append(StackedImbalance(side, start, prev))  # type: ignore[arg-type]
            start = prev = r
    return sorted(out, key=lambda s: (s.low_row, s.side))
