"""PostgreSQL persistence (psycopg 3, sync calls run in a worker thread by the async wrappers).

Idempotent writes: trades use ON CONFLICT DO NOTHING on (iid, ts, seq) so a reconnect that
replays ticks cannot double-count; bars upsert so a forming bar can be overwritten until closed.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from ofx.domain import AggressorSide, Instrument, Trade
from ofx.orderflow.footprint import FootprintBar
from ofx.orderflow.observation import Observation

SIDE_TO_INT = {AggressorSide.ASK: 1, AggressorSide.BID: -1, AggressorSide.UNKNOWN: 0}
INT_TO_SIDE = {v: k for k, v in SIDE_TO_INT.items()}

SQL_UPSERT_INSTRUMENT = (
    "INSERT INTO instruments (iid, symbol, exchange, provider, tick_size, lot_size, tz) VALUES (%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (iid) DO UPDATE SET symbol=EXCLUDED.symbol, tick_size=EXCLUDED.tick_size, lot_size=EXCLUDED.lot_size, tz=EXCLUDED.tz")
SQL_INSERT_TRADE = (
    "INSERT INTO trades (iid, ts, seq, price, qty, side, side_method) VALUES (%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (iid, ts, seq) DO NOTHING")
SQL_SELECT_TRADES = (
    "SELECT ts, price, qty, side, seq, side_method FROM trades WHERE iid = %s AND ts >= %s AND ts < %s ORDER BY ts, seq")
SQL_UPSERT_BAR = (
    "INSERT INTO footprint_bars (iid, timeframe, ts_open, tick_size, open, high, low, close, volume, delta, cvd_close, "
    "unknown_share, quality, rows, closed) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON CONFLICT (iid, timeframe, ts_open, tick_size) DO UPDATE SET open=EXCLUDED.open, high=EXCLUDED.high, "
    "low=EXCLUDED.low, close=EXCLUDED.close, volume=EXCLUDED.volume, delta=EXCLUDED.delta, cvd_close=EXCLUDED.cvd_close, "
    "unknown_share=EXCLUDED.unknown_share, quality=EXCLUDED.quality, rows=EXCLUDED.rows, closed=EXCLUDED.closed "
    "WHERE footprint_bars.closed = false")  # a closed bar is immutable
SQL_INSERT_OBS = (
    "INSERT INTO observations (iid, kind, ts_start, ts_end, data_quality, confidence, payload) VALUES (%s,%s,%s,%s,%s,%s,%s)")
SQL_SELECT_OBS = (
    "SELECT payload FROM observations WHERE iid = %s AND ts_start >= %s AND ts_start < %s ORDER BY ts_start")
ALL_SQL = (SQL_UPSERT_INSTRUMENT, SQL_INSERT_TRADE, SQL_SELECT_TRADES, SQL_UPSERT_BAR, SQL_INSERT_OBS, SQL_SELECT_OBS)


class PgStore:
    def __init__(self, conn: Any) -> None:
        self.conn = conn  # a psycopg connection (autocommit off; we commit per call)

    @classmethod
    def connect(cls, dsn: str) -> PgStore:  # pragma: no cover - needs a server (covered by the integration test)
        import psycopg
        return cls(psycopg.connect(dsn))

    def upsert_instrument(self, ins: Instrument, provider: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(SQL_UPSERT_INSTRUMENT, (ins.iid, ins.symbol, ins.exchange, provider, ins.tick_size, ins.lot_size, ins.tz))
        self.conn.commit()

    def insert_trades(self, iid: str, trades: Iterable[Trade]) -> None:
        rows = [(iid, t.ts, t.seq, Decimal(str(t.price)), Decimal(str(t.qty)), SIDE_TO_INT[t.side], t.side_method) for t in trades]
        with self.conn.cursor() as cur:
            cur.executemany(SQL_INSERT_TRADE, rows)
        self.conn.commit()

    def load_trades(self, iid: str, start: datetime, end: datetime) -> list[Trade]:
        with self.conn.cursor() as cur:
            cur.execute(SQL_SELECT_TRADES, (iid, start, end))
            return [Trade(ts, float(p), float(q), INT_TO_SIDE[s], int(seq), m) for ts, p, q, s, seq, m in cur.fetchall()]

    def upsert_bar(self, iid: str, timeframe: str, bar: FootprintBar, closed: bool) -> None:
        rows = {str(r): [c.bid_vol, c.ask_vol] for r, c in sorted(bar.rows.items())}
        with self.conn.cursor() as cur:
            cur.execute(SQL_UPSERT_BAR, (iid, timeframe, bar.ts_open, Decimal(str(bar.tick)), Decimal(str(bar.open_px)),
                                         Decimal(str(bar.high_px)), Decimal(str(bar.low_px)), Decimal(str(bar.close_px)),
                                         Decimal(str(bar.volume)), Decimal(str(bar.delta)), Decimal(str(bar.cvd_close)),
                                         bar.unknown_share, bar.quality.value, json.dumps(rows), closed))
        self.conn.commit()

    def insert_observations(self, iid: str, obs: Sequence[Observation]) -> None:
        rows = [(iid, o.kind, o.ts_start, o.ts_end, o.data_quality.value, o.confidence, json.dumps(o.to_dict())) for o in obs]
        with self.conn.cursor() as cur:
            cur.executemany(SQL_INSERT_OBS, rows)
        self.conn.commit()

    def load_observations(self, iid: str, start: datetime, end: datetime) -> list[dict]:
        with self.conn.cursor() as cur:
            cur.execute(SQL_SELECT_OBS, (iid, start, end))
            return [r[0] for r in cur.fetchall()]


class StoredTradesProvider:
    """Replays recorded trades through the same Service as a live feed would use."""

    def __init__(self, store: PgStore, capabilities: Any) -> None:
        self._s, self.capabilities = store, capabilities

    async def trades(self, iid: str, start: datetime, end: datetime) -> Sequence[Trade]:
        return await asyncio.to_thread(self._s.load_trades, iid, start, end)

    async def instruments(self) -> Sequence[Instrument]:
        return []

    async def candles(self, iid: str, start: datetime, end: datetime, timeframe: str) -> Sequence[Any]:
        raise NotImplementedError("candles are served from the candles table (not wired in this skeleton)")
