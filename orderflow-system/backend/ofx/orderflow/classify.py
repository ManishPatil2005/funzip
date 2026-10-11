"""Aggressor-side classification.

When the exchange provides the aggressor flag (CME MDP 3.0 tag 5797, crypto
venues that tag the taker) the data is EXACT. Otherwise the side is inferred
and the result is ESTIMATED. Trades that cannot be classified stay UNKNOWN;
they are never silently assigned to a side.
"""
from __future__ import annotations

import bisect
from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import timedelta
from enum import Enum

from ofx.domain import AggressorSide, DataQuality, Quote, Trade


class Method(str, Enum):
    EXCHANGE = "exchange"  # keep the provider's flag
    QUOTE = "quote_rule"  # at/above ask -> ASK, at/below bid -> BID
    TICK = "tick_rule"  # up-tick -> ASK, down-tick -> BID, zero-tick inherits
    LEE_READY = "lee_ready"  # quote rule, tick rule for midpoint trades


def quality_for(method: Method) -> DataQuality:
    return DataQuality.EXACT if method is Method.EXCHANGE else DataQuality.ESTIMATED


def classify_trades(
    trades: Iterable[Trade],
    quotes: Sequence[Quote] = (),
    method: Method = Method.LEE_READY,
    quote_lag: timedelta = timedelta(0),
) -> list[Trade]:
    """Return trades with side and side_method set according to `method`.

    quote_lag compensates for quotes arriving after the trade they relate to
    (common with 1-second snapshot feeds): the quote used is the latest one
    at or before (trade.ts - quote_lag).
    """
    ordered = sorted(trades, key=lambda t: (t.ts, t.seq))
    q_sorted = sorted(quotes, key=lambda q: q.ts)
    q_ts = [q.ts for q in q_sorted]
    out: list[Trade] = []
    last_price: float | None = None
    last_side = AggressorSide.UNKNOWN

    for t in ordered:
        side = AggressorSide.UNKNOWN
        used = "none"
        if method is Method.EXCHANGE:
            if t.side is not AggressorSide.UNKNOWN:
                side, used = t.side, Method.EXCHANGE.value
        else:
            if method in (Method.QUOTE, Method.LEE_READY) and q_sorted:
                i = bisect.bisect_right(q_ts, t.ts - quote_lag) - 1
                if i >= 0:
                    q = q_sorted[i]
                    if q.ask > q.bid:  # ignore locked/crossed quotes
                        if t.price >= q.ask:
                            side, used = AggressorSide.ASK, Method.QUOTE.value
                        elif t.price <= q.bid:
                            side, used = AggressorSide.BID, Method.QUOTE.value
            if side is AggressorSide.UNKNOWN and method in (Method.TICK, Method.LEE_READY):
                if last_price is not None:
                    if t.price > last_price:
                        side, used = AggressorSide.ASK, Method.TICK.value
                    elif t.price < last_price:
                        side, used = AggressorSide.BID, Method.TICK.value
                    elif last_side is not AggressorSide.UNKNOWN:
                        side, used = last_side, Method.TICK.value
        if side is not AggressorSide.UNKNOWN:
            last_side = side
        last_price = t.price
        out.append(replace(t, side=side, side_method=used))
    return out


def agreement(a: Sequence[Trade], b: Sequence[Trade]) -> tuple[float, int]:
    """Fraction of trades where two classifications agree, among those both classified.

    A low score means the side estimate is unreliable on this data (for example
    quotes are stale or sampled too slowly) and confidence should be reduced.
    """
    if len(a) != len(b):
        raise ValueError("classifications must cover the same trades")
    both = [(x.side, y.side) for x, y in zip(a, b) if AggressorSide.UNKNOWN not in (x.side, y.side)]
    if not both:
        return 0.0, 0
    return sum(1 for x, y in both if x is y) / len(both), len(both)


def split_bar_volume(volume: float, open_: float, high: float, low: float, close: float) -> tuple[float, float]:
    """BAR_APPROXIMATED split of bar volume into (ask_volume, bid_volume).

    Close-location rule: ask share = (close - low) / (high - low). For a flat
    bar the split follows the close vs open direction, else is even. This is a
    crude proxy; results carry DataQuality.BAR_APPROXIMATED.
    """
    if volume <= 0:
        return 0.0, 0.0
    if high > low:
        share = (close - low) / (high - low)
    elif close > open_:
        share = 1.0
    elif close < open_:
        share = 0.0
    else:
        share = 0.5
    share = min(1.0, max(0.0, share))
    return volume * share, volume * (1.0 - share)
