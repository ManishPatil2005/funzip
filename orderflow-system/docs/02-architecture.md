# 02 · Architecture Report

## 1. Shape: modular monolith + one stream worker
```
 Providers (Angel | Delta | Synthetic)         ── port: MarketDataProvider (ofx/providers/base.py)
        │ trades / depth / quotes / candles
        ▼
 Ingest worker ──► classify (aggressor) ──► Redis Streams (hot, ~minutes) ──► WebSocket hub ──► React client
        │                                       │
        ▼                                       ▼
 TimescaleDB (trades, depth, bars, profiles)   Analytics services (footprint, profile, TPO, DOM, detectors)
        ▲                                       │
        └──────────── REST API (FastAPI) ◄──────┘  → Observation objects only (never a trade instruction)
```
**Decision: monolith first.** One deployable, one codebase, clear module boundaries (`domain`, `orderflow`, `providers`, `api`). Reason: the load (a few instruments, one user class) does not justify distributed systems; module seams let us extract the ingest worker later. (Matches ADR-004 awaiting approval.)

## 2. Folder structure (as built)
```
backend/ofx/domain.py          canonical models, ASK/BID enum, DataQuality
backend/ofx/language.py        banned-word linter
backend/ofx/orderflow/         classify, footprint, volume_profile, market_profile, orderbook, heatmap, detectors, observation
backend/ofx/providers/         base (ports), synthetic, delta (skeleton + HMAC), angel (skeleton)
backend/ofx/api/               service, hub (WS fan-out), cache (memory/redis)
backend/ofx/main.py            FastAPI app factory
backend/migrations/0001_schema.sql
frontend/src/lib/              color, layout, net (pure, unit-tested)
frontend/src/components/       FootprintLayer (canvas overlay)
```

## 3. Technical decisions and why
| Decision | Why | Trade-off |
|---|---|---|
| Integer price rows `round(price/tick)` | Float floor errors (100.3/0.1 → 1002) break bucketing; test-pinned | Needs tick size per instrument |
| Aggressor enum ASK/BID, not BUY/SELL | No code path can read as an instruction | Slightly unfamiliar naming |
| Unknown-side volume kept separate | Never invent a side; delta shows its own uncertainty | Delta can understate |
| Every output is an `Observation` with quality, method, confidence, alternatives, limitations | Teaching tool, honest uncertainty | More verbose output |
| Confidence capped by data tier (1.0 / 0.6 / 0.35) | Estimated data cannot yield high confidence | Rules are judgement-based [I] |
| Confirmed-pivot detection only | No repaint; signals never vanish | Detection lags `right` bars |
| Causal level building for sweeps | Later pivots cannot change an earlier level (a bug found and fixed in tests) | — |
| TimescaleDB over plain Postgres | Hypertables, compression, retention policies for tick data | Extra extension to operate |
| Redis for hot fan-out/cache | Cheap pub/sub and TTL | Another service; memory cache fallback exists |
| Canvas overlay on Lightweight Charts | Library has no footprint series; overlay synced via `timeToCoordinate` / `priceToCoordinate` | Must redraw on range change |
| Bounded WS queues, drop-oldest | Slow client cannot stall others | Client sees gaps (counter sent) |
| Optional API key, constant-time compare | Simple secure default for single-tenant | Not multi-user auth (future) |

## 4. WebSocket design
`GET /ws/v1/stream?topic=<iid>:<kind>` ; server pushes JSON `{type, ts, data}`; `dropped` count appears after backpressure. Client reconnects with exponential backoff + jitter (500 ms → 15 s cap). Closed bars are immutable; the forming bar is sent as `closed:false` and replaced.

## 5. Caching strategy
Closed-bar responses cached by `(iid, tf, tick, start, end)`; forming bar never cached. Memory FIFO (bounded) in dev; Redis with TTL in production behind the same `Cache` protocol.

## 6. Security
API key header (`x-api-key`), CORS allow-list from env, read-only GET surface, spans capped at 2 days, parameters validated (422/400), secrets only from environment (names: `ANGEL_SMARTAPI_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_PIN`, `ANGEL_TOTP_SECRET`, `DELTA_EXCHANGE_API_KEY`, `DELTA_EXCHANGE_SECRET`); provider `__repr__` hides credentials; non-root container.

## 7. Scaling path (not built)
Extract ingest worker → add Kafka only if >1 consumer group needs replay; shard instruments across workers; pre-aggregate footprint bars in a continuous aggregate.
