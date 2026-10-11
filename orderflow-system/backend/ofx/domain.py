"""Canonical domain models. Every provider adapter translates into these.

Naming note: the aggressor side uses ASK/BID (which side of the book the trade
executed against) rather than BUY/SELL, so no code path can be mistaken for a
trade instruction. "Buyer-initiated" == ASK, "seller-initiated" == BID.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AggressorSide(str, Enum):
    ASK = "ask"  # buyer-initiated: the trade lifted the offer
    BID = "bid"  # seller-initiated: the trade hit the bid
    UNKNOWN = "unknown"


class DataQuality(str, Enum):
    """How trustworthy the buyer/seller split is. Always shown next to outputs."""

    EXACT = "exact"  # exchange-provided aggressor flag
    ESTIMATED = "estimated"  # inferred (quote rule, tick rule, Lee-Ready)
    BAR_APPROXIMATED = "bar_approximated"  # inferred from OHLCV only


_RANK = {DataQuality.EXACT: 2, DataQuality.ESTIMATED: 1, DataQuality.BAR_APPROXIMATED: 0}


def weakest(*qualities: DataQuality) -> DataQuality:
    """A result is only as good as its weakest input."""
    return min(qualities, key=lambda q: _RANK[q])


def price_to_row(price: float, tick: float) -> int:
    """Map a price to its integer row index. round() avoids float floor errors."""
    return int(round(price / tick))


def row_to_price(row: int, tick: float) -> float:
    return round(row * tick, 10)


@dataclass(frozen=True, slots=True)
class Instrument:
    iid: str
    symbol: str
    exchange: str
    tick_size: float
    lot_size: float = 1.0
    tz: str = "UTC"


@dataclass(frozen=True, slots=True)
class Trade:
    ts: datetime
    price: float
    qty: float
    side: AggressorSide = AggressorSide.UNKNOWN
    seq: int = 0
    side_method: str = "none"  # exchange | quote_rule | tick_rule | lee_ready | none

    def __post_init__(self) -> None:
        if self.ts.tzinfo is None:
            raise ValueError("Trade.ts must be timezone-aware (UTC)")
        if self.price <= 0 or self.qty <= 0:
            raise ValueError("Trade price and qty must be positive")


@dataclass(frozen=True, slots=True)
class Quote:
    ts: datetime
    bid: float
    ask: float
    bid_qty: float = 0.0
    ask_qty: float = 0.0


@dataclass(frozen=True, slots=True)
class DepthLevel:
    price: float
    qty: float


@dataclass(frozen=True, slots=True)
class DepthSnapshot:
    ts: datetime
    bids: tuple[DepthLevel, ...]  # best (highest) first
    asks: tuple[DepthLevel, ...]  # best (lowest) first
    seq: int = 0


@dataclass(frozen=True, slots=True)
class Candle:
    ts_open: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
