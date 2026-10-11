# 03 · Database Design (PostgreSQL 15+, TimescaleDB optional)
Migrations: `0001_schema.sql` (plain Postgres tables, **executed against a real PostgreSQL 16 in tests**) and `0002_timescale.sql` (hypertables, compression, retention — **syntax-checked only; not executed**, the TimescaleDB extension was unavailable in my sandbox). Persistence code: `ofx/storage/pg.py` (idempotent trade inserts, closed-bar immutability, observation store, replay provider).

Retention/compression policies in the table below take effect only after 0002 is applied.

**Conventions.** UTC `timestamptz`; prices `numeric(24,8)` (exact, no float drift); quantity `numeric(24,8)`; price rows `bigint = round(price/tick)`; sides `smallint` (-1 bid-hit, 1 ask-lift, 0 unknown).

| Table | Key columns | Primary key | Indexes / policy | Retention |
|---|---|---|---|---|
| `instruments` | iid, symbol, exchange, provider, tick_size, lot_size, tz, meta | iid | `(exchange, symbol)` | permanent |
| `sessions` | iid, session_start, session_end, kind | (iid, session_start) | PK | permanent |
| `trades` (hypertable, 1-day chunks) | iid, ts, seq, price, qty, side, side_method | (iid, ts, seq) | compress after 3 d, segmentby iid | **90 days** |
| `candles` (hypertable, 30-day) | iid, timeframe, ts_open, OHLC, volume, source | (iid, timeframe, ts_open) | CHECK high ≥ low | 5 years |
| `orderbook_snapshots` (hypertable, 6 h) | iid, ts, seq, bids jsonb, asks jsonb | (iid, ts, seq) | compress after 1 d | **14 days** |
| `footprint_bars` (hypertable, 7 d) | iid, timeframe, ts_open, tick_size, OHLC, volume, delta, cvd_close, unknown_share, quality, rows jsonb, closed | (iid, timeframe, ts_open, tick_size) | — | 2 years |
| `profiles` | iid, kind(volume/tpo), scope, period_start, tick_size, rows, levels, approximated | (iid, kind, scope, period_start, tick_size) | `(iid, kind, scope, period_start DESC)` | permanent |
| `observations` (hypertable, 30 d) | id, iid, kind, ts_start, ts_end, data_quality, confidence, payload | (id, ts_start) | `(iid, kind, ts_start DESC)` | permanent |

## Decisions
- **Trades at tick level, short retention.** Highest volume; footprint bars can be rebuilt from trades, and stored bars (2 y) survive after raw trades expire.
- **Footprint rows as jsonb** `{row:[bid,ask]}`: variable row count per bar; avoids a billion-row child table. Cost: no SQL-side per-row filtering (acceptable; filtering done in the service).
- **Depth snapshots as jsonb arrays**, 14-day retention: heatmaps only need recent history; storage cost dominates.
- **`side_method` stored per trade** so quality can always be recomputed and audited.
- **`unknown_share` and `quality` on bars** so the UI never shows an unlabelled number.
- Retention values are **my defaults [I]**; tune to storage budget.
