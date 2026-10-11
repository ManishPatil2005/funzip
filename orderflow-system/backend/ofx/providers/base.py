"""Provider ports. Analytics depend on these protocols, never on a vendor SDK.

Each provider declares what it can truthfully supply (`Capabilities`); the service layer
uses that to label data quality and to refuse features the feed cannot support.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ofx.domain import Candle, DataQuality, DepthSnapshot, Instrument, Quote, Trade


@dataclass(frozen=True)
class Capabilities:
    name: str
    trades: bool  # tick-level prints available
    aggressor_flag: bool  # exchange supplies the aggressor side on each trade
    depth_levels: int  # 0 = no depth
    historical_trades: bool
    historical_candles: bool
    max_candles_per_request: int = 0
    notes: str = ""

    @property
    def trade_quality(self) -> DataQuality:
        if self.trades and self.aggressor_flag:
            return DataQuality.EXACT
        return DataQuality.ESTIMATED if self.trades else DataQuality.BAR_APPROXIMATED


class MarketDataProvider(Protocol):
    capabilities: Capabilities

    async def instruments(self) -> Sequence[Instrument]: ...
    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Candle]: ...
    async def trades(self, iid: str, start: datetime, end: datetime) -> Sequence[Trade]: ...
    def stream_trades(self, iid: str) -> AsyncIterator[Trade]: ...
    def stream_depth(self, iid: str) -> AsyncIterator[DepthSnapshot]: ...
    def stream_quotes(self, iid: str) -> AsyncIterator[Quote]: ...


class ProviderUnsupported(RuntimeError):
    """Raised when a feature is requested that the feed cannot supply."""
