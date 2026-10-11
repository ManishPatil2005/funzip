"""Live ingest: provider trade stream -> side estimation -> forming/closed footprint bars -> hub."""
from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Callable, Hashable
from datetime import datetime, timedelta
from typing import Any

from ofx.api.hub import Hub
from ofx.api.service import bar_to_dict
from ofx.domain import AggressorSide, Trade
from ofx.orderflow.footprint import FootprintBar, ImbalanceConfig, build_footprint, utc_day
from ofx.providers.base import MarketDataProvider


class StreamingTickRule:
    """Stateful tick rule for feeds without an aggressor flag. Zero-tick inherits the last side;
    the very first print stays UNKNOWN (no honest basis for a side)."""

    def __init__(self) -> None:
        self._last_px: float | None = None
        self._last_side = AggressorSide.UNKNOWN

    def __call__(self, t: Trade) -> Trade:
        if t.side is not AggressorSide.UNKNOWN:
            self._last_px, self._last_side = t.price, t.side
            return t
        side = self._last_side
        if self._last_px is not None and t.price != self._last_px:
            side = AggressorSide.ASK if t.price > self._last_px else AggressorSide.BID
        self._last_px, self._last_side = t.price, side
        return dataclasses.replace(t, side=side, side_method="tick_rule" if side is not AggressorSide.UNKNOWN else "none")


class LiveFootprint:
    """Incremental bars. Closed bars are immutable; only the forming bar is recomputed."""

    def __init__(self, tick: float, timeframe: timedelta, session_key: Callable[[datetime], Hashable] = utc_day,
                 max_buffer: int = 200_000) -> None:
        self.tick, self.tf, self.session_key, self.max_buffer = tick, timeframe, session_key, max_buffer
        self._buf: list[Trade] = []
        self._start: datetime | None = None
        self._cvd = 0.0
        self._session: Hashable | None = None

    def _build(self) -> FootprintBar | None:
        bars = build_footprint(self._buf, self.tick, self.tf)
        if not bars:
            return None
        b = bars[0]
        key = self.session_key(b.ts_open)
        base = 0.0 if key != self._session else self._cvd
        b.cvd_open, b.cvd_close = base, base + b.delta
        return b

    def on_trade(self, t: Trade) -> tuple[FootprintBar, FootprintBar | None]:
        """Returns (forming_bar, just_closed_bar_or_None)."""
        start = build_footprint([t], self.tick, self.tf)[0].ts_open
        closed = None
        if self._start is not None and start > self._start:
            closed = self._build()
            if closed is not None:
                self._cvd, self._session = closed.cvd_close, self.session_key(closed.ts_open)
            self._buf = []
        elif self._start is not None and start < self._start:
            raise ValueError("out-of-order trade for an already closed bar")  # caller decides to drop/log
        self._start = start
        if len(self._buf) >= self.max_buffer:
            raise OverflowError("bar buffer limit reached")
        self._buf.append(t)
        forming = self._build()
        assert forming is not None
        forming.quality = forming.quality
        return forming, closed


class Recorder:
    """Persists the live stream forward in time (Angel offers no historical ticks, so recording IS the history).

    Trades are buffered and written in batches (idempotent on (iid, ts, seq)); closed bars are upserted once.
    The store is any object with insert_trades / upsert_bar (PgStore in production, a fake in tests).
    """

    def __init__(self, store: Any, iid: str, timeframe_label: str, batch: int = 200) -> None:
        self.store, self.iid, self.tf, self.batch = store, iid, timeframe_label, batch
        self._buf: list[Trade] = []

    def on_trade(self, t: Trade) -> None:
        self._buf.append(t)
        if len(self._buf) >= self.batch:
            self.flush()

    def on_closed(self, bar: FootprintBar) -> None:
        self.flush()
        self.store.upsert_bar(self.iid, self.tf, bar, True)

    def flush(self) -> None:
        if self._buf:
            self.store.insert_trades(self.iid, self._buf)
            self._buf = []


async def run_ingest(provider: MarketDataProvider, iid: str, tick: float, timeframe: timedelta, hub: Hub,
                     stop: asyncio.Event | None = None, on_closed: Callable[[FootprintBar], None] | None = None,
                     on_trade: Callable[[Trade], None] | None = None) -> int:
    """Consume the provider stream until it ends or `stop` is set. Returns trades processed."""
    cfg = ImbalanceConfig()
    live = LiveFootprint(tick, timeframe)
    rule = None if provider.capabilities.aggressor_flag else StreamingTickRule()
    topic, n = f"{iid}:footprint", 0
    async for t in provider.stream_trades(iid):
        if stop is not None and stop.is_set():
            break
        if rule is not None:
            t = rule(t)
        try:
            forming, closed = live.on_trade(t)
        except ValueError:
            continue  # late trade for a closed bar: dropped, never rewrites history
        n += 1
        if on_trade:
            on_trade(t)
        if closed is not None:
            hub.publish(topic, {"type": "footprint", "closed": True, "bar": _dto(closed, cfg)})
            if on_closed:
                on_closed(closed)
        hub.publish(topic, {"type": "footprint", "closed": False, "bar": _dto(forming, cfg)})
    return n


def _dto(b: FootprintBar, cfg: ImbalanceConfig) -> dict[str, Any]:
    return bar_to_dict(b, cfg, 3)
