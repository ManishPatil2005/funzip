"""DOM: order book state, imbalance, liquidity walls, spoof-like pattern and iceberg-like logic.

Spoof and iceberg logic are PATTERN detectors on observable data. A resting order's
true intent and any hidden (reserve) quantity are not observable; outputs are
phrased as "consistent with" and always carry ESTIMATED quality at best.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median
from typing import Literal

from ofx.domain import AggressorSide, DataQuality, DepthLevel, DepthSnapshot, Trade, price_to_row, row_to_price
from ofx.orderflow.observation import Observation, cap_confidence

Side = Literal["bid", "ask"]


class OrderBook:
    def __init__(self, tick: float) -> None:
        self.tick = tick
        self.bids: dict[int, float] = {}
        self.asks: dict[int, float] = {}

    def apply_snapshot(self, snap: DepthSnapshot) -> None:
        self.bids = {price_to_row(l.price, self.tick): l.qty for l in snap.bids if l.qty > 0}
        self.asks = {price_to_row(l.price, self.tick): l.qty for l in snap.asks if l.qty > 0}

    def apply_update(self, side: Side, price: float, qty: float) -> None:
        book = self.bids if side == "bid" else self.asks
        r = price_to_row(price, self.tick)
        if qty <= 0:
            book.pop(r, None)
        else:
            book[r] = qty

    @property
    def best_bid_row(self) -> int | None:
        return max(self.bids) if self.bids else None

    @property
    def best_ask_row(self) -> int | None:
        return min(self.asks) if self.asks else None

    @property
    def spread_ticks(self) -> int | None:
        b, a = self.best_bid_row, self.best_ask_row
        return None if b is None or a is None else a - b

    def levels(self, side: Side, n: int) -> list[DepthLevel]:
        if side == "bid":
            rows = sorted(self.bids, reverse=True)[:n]
            return [DepthLevel(row_to_price(r, self.tick), self.bids[r]) for r in rows]
        rows = sorted(self.asks)[:n]
        return [DepthLevel(row_to_price(r, self.tick), self.asks[r]) for r in rows]


def book_imbalance(book: OrderBook, levels: int = 5, weighting: Literal["flat", "inverse_distance"] = "inverse_distance") -> float | None:
    """(B - A) / (B + A) over the top `levels` per side, in [-1, 1].

    Positive: more resting quantity on the bid side. Level i (0 = best) is weighted
    1/(i+1) under inverse_distance, so quantity near the touch counts more. Resting
    size is a snapshot of intent, not of executed flow, and can be withdrawn.
    """
    bids, asks = book.levels("bid", levels), book.levels("ask", levels)
    if not bids and not asks:
        return None
    w = (lambda i: 1.0) if weighting == "flat" else (lambda i: 1.0 / (i + 1))
    b = sum(l.qty * w(i) for i, l in enumerate(bids))
    a = sum(l.qty * w(i) for i, l in enumerate(asks))
    return None if b + a == 0 else (b - a) / (b + a)


@dataclass(frozen=True)
class Wall:
    side: Side
    price: float
    qty: float
    ratio: float  # qty relative to the median level quantity
    distance_ticks: int  # from the touch


def find_walls(book: OrderBook, side: Side, levels: int = 20, k: float = 3.0, min_qty: float = 0.0) -> list[Wall]:
    """Liquidity walls: levels with quantity >= k x the median of the inspected levels."""
    lv = book.levels(side, levels)
    if len(lv) < 3:
        return []
    ref = median(l.qty for l in lv) or mean(l.qty for l in lv)
    best = book.best_bid_row if side == "bid" else book.best_ask_row
    out = []
    for l in lv:
        if l.qty >= k * ref and l.qty >= min_qty and best is not None:
            out.append(Wall(side, l.price, l.qty, l.qty / ref if ref else float("inf"), abs(price_to_row(l.price, book.tick) - best)))
    return out


# ------------------------------------------------------------------ wall lifecycle
@dataclass
class _WallState:
    first_ts: datetime
    first_distance: int
    peak_qty: float
    executed: float = 0.0


@dataclass(frozen=True)
class WallEvent:
    ts: datetime
    side: Side
    price: float
    peak_qty: float
    lifetime_s: float
    executed_share: float
    distance_at_removal: int
    approached: bool
    outcome: Literal["pulled", "consumed"]


class WallTracker:
    """Follow walls across book updates and emit an event when one disappears.

    consumed: executed volume at the level explains most of the removal.
    pulled: removed without being traded through (cancelled or moved).
    """

    def __init__(self, tick: float, levels: int = 20, k: float = 3.0, min_qty: float = 0.0,
                 vanish_fraction: float = 0.2, consumed_share: float = 0.5, approach_ticks: int = 3) -> None:
        self.tick, self.levels, self.k, self.min_qty = tick, levels, k, min_qty
        self.vanish_fraction, self.consumed_share, self.approach_ticks = vanish_fraction, consumed_share, approach_ticks
        self._walls: dict[tuple[Side, int], _WallState] = {}

    def on_trades(self, trades: Iterable[Trade]) -> None:
        """Executed volume at a wall's price counts toward 'consumed'."""
        for t in trades:
            r = price_to_row(t.price, self.tick)
            for side in ("bid", "ask"):
                st = self._walls.get((side, r))  # type: ignore[arg-type]
                if st is not None:
                    st.executed += t.qty

    def on_book(self, ts: datetime, book: OrderBook) -> list[WallEvent]:
        events: list[WallEvent] = []
        for side in ("bid", "ask"):
            current = {w.price: w for w in find_walls(book, side, self.levels, self.k, self.min_qty)}  # type: ignore[arg-type]
            best = book.best_bid_row if side == "bid" else book.best_ask_row
            qty_map = book.bids if side == "bid" else book.asks
            for price, w in current.items():
                r = price_to_row(price, self.tick)
                st = self._walls.get((side, r))  # type: ignore[arg-type]
                if st is None:
                    self._walls[(side, r)] = _WallState(ts, w.distance_ticks, w.qty)  # type: ignore[index]
                else:
                    st.peak_qty = max(st.peak_qty, w.qty)
            for (s, r), st in list(self._walls.items()):
                if s != side:
                    continue
                qty_now = qty_map.get(r, 0.0)
                if qty_now > self.vanish_fraction * st.peak_qty:
                    continue
                dist = abs(r - best) if best is not None else 0
                share = min(1.0, st.executed / st.peak_qty) if st.peak_qty else 0.0
                events.append(WallEvent(
                    ts, side, row_to_price(r, self.tick), st.peak_qty, (ts - st.first_ts).total_seconds(), share, dist,
                    approached=dist <= self.approach_ticks and dist < st.first_distance,
                    outcome="consumed" if share >= self.consumed_share else "pulled",
                ))
                del self._walls[(s, r)]  # type: ignore[arg-type]
        return events


def spoof_like_pattern(
    events: Sequence[WallEvent], window_s: float = 60.0, min_events: int = 3, max_lifetime_s: float = 10.0,
    max_executed_share: float = 0.1, feed_quality: DataQuality = DataQuality.ESTIMATED,
) -> list[Observation]:
    """Repeated large resting quantity that appears, is not traded, and is withdrawn as price approaches.

    Per side, count 'pulled' wall events with short lifetime, ~no executions and an approach
    within the window. Needs event-level L2 to be meaningful; from 1-second snapshots the
    timing is too coarse, so the caller should pass feed_quality=ESTIMATED (the cap in
    confidence then applies). This is a pattern description, not an inference of intent.
    """
    out: list[Observation] = []
    for side in ("bid", "ask"):
        cand = sorted(
            (e for e in events if e.side == side and e.outcome == "pulled" and e.approached
             and e.lifetime_s <= max_lifetime_s and e.executed_share <= max_executed_share),
            key=lambda e: e.ts,
        )
        i = 0
        while i < len(cand):
            j = i
            while j + 1 < len(cand) and (cand[j + 1].ts - cand[i].ts).total_seconds() <= window_s:
                j += 1
            group = cand[i:j + 1]
            if len(group) >= min_events:
                prices = [g.price for g in group]
                conf = cap_confidence(min(1.0, len(group) / (2 * min_events)) * 0.7, feed_quality)
                side_txt = "bid" if side == "bid" else "offer"
                out.append(Observation(
                    kind="spoof_like_pattern", ts_start=group[0].ts, ts_end=group[-1].ts,
                    summary=(f"{len(group)} large resting {side_txt} quantities were withdrawn within {max_lifetime_s:.0f}s "
                             f"of appearing, without being traded, as price approached."),
                    data_quality=feed_quality, method="wall_lifecycle", confidence=conf,
                    price_low=min(prices), price_high=max(prices),
                    evidence={"events": len(group), "mean_lifetime_s": round(mean(g.lifetime_s for g in group), 2),
                              "peak_qty_total": sum(g.peak_qty for g in group)},
                    alternatives=("Passive participants adjusting quotes as volatility changed",
                                  "Algorithmic market makers repricing, which is routine behaviour",
                                  "Intent cannot be observed from market data"),
                    limitations=("Pattern on observable depth only. Cancelled orders are not attributable to an actor, and "
                                 "1-second snapshot feeds can miss short-lived orders. Not evidence of manipulation."),
                    teaching_ref="liquidity-walls-and-spoof-patterns",
                ))
                i = j + 1
            else:
                i += 1
    return out


# ---------------------------------------------------------------------- iceberg-like
@dataclass
class _IceState:
    max_displayed: float
    executed: float = 0.0
    executed_since_book: float = 0.0
    refills: int = 0
    first_ts: datetime | None = None
    emitted: bool = False


class IcebergTracker:
    """Detect levels that keep absorbing executions while displaying little size.

    A level is iceberg-like when cumulative executed volume exceeds `multiple` x the largest
    displayed quantity seen there AND the level was replenished at least `min_refills` times
    (displayed size restored after executions). Hidden reserve size is never observed; this
    is an inference from refill behaviour. Requires trades and depth that can be aligned in time.
    """

    def __init__(self, tick: float, multiple: float = 3.0, min_refills: int = 3, refill_fraction: float = 0.5) -> None:
        self.tick, self.multiple, self.min_refills, self.refill_fraction = tick, multiple, min_refills, refill_fraction
        self._levels: dict[tuple[Side, int], _IceState] = {}

    def on_trade(self, ts: datetime, trade: Trade, book: OrderBook) -> None:
        """An ASK-aggressor trade consumes the ask side; a BID-aggressor trade consumes the bid side."""
        if trade.side is AggressorSide.UNKNOWN:
            return
        side: Side = "ask" if trade.side is AggressorSide.ASK else "bid"
        r = price_to_row(trade.price, self.tick)
        displayed = (book.asks if side == "ask" else book.bids).get(r, 0.0)
        st = self._levels.get((side, r))
        if st is None:
            st = _IceState(max_displayed=max(displayed, trade.qty), first_ts=ts)
            self._levels[(side, r)] = st
        st.max_displayed = max(st.max_displayed, displayed)
        st.executed += trade.qty
        st.executed_since_book += trade.qty

    def on_book(self, ts: datetime, book: OrderBook) -> list[Observation]:
        out: list[Observation] = []
        for (side, r), st in list(self._levels.items()):
            qty_map = book.asks if side == "ask" else book.bids
            displayed = qty_map.get(r, 0.0)
            if st.executed_since_book > 0:
                if displayed >= self.refill_fraction * st.max_displayed and displayed > 0:
                    st.refills += 1
                st.executed_since_book = 0.0
            if displayed == 0 and st.refills == 0:
                del self._levels[(side, r)]
                continue
            if (not st.emitted and st.refills >= self.min_refills
                    and st.executed >= self.multiple * st.max_displayed):
                st.emitted = True
                conf = cap_confidence(min(1.0, st.executed / (2 * self.multiple * st.max_displayed)), DataQuality.ESTIMATED)
                price = row_to_price(r, self.tick)
                out.append(Observation(
                    kind="iceberg_like_level", ts_start=st.first_ts or ts, ts_end=ts,
                    summary=(f"{st.executed:.0f} traded at {price} on the {side} side against a displayed maximum of "
                             f"{st.max_displayed:.0f}, with the level replenished {st.refills} times."),
                    data_quality=DataQuality.ESTIMATED, method="refill_behaviour", confidence=conf,
                    price_low=price, price_high=price,
                    evidence={"executed": st.executed, "max_displayed": st.max_displayed, "refills": st.refills},
                    alternatives=("Several participants queueing at the same price", "An algorithm replenishing displayed size"),
                    limitations="Reserve quantity is not observable; this infers it from refills and cannot identify the participant.",
                    teaching_ref="iceberg-orders",
                ))
        return out
