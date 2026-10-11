# Data Provider Layer

Goal: swap or add a data source (Zerodha, Upstox, Dhan, IBKR, Polygon, NSE, BSE, Binance, Delta, CQG, Rithmic)
with **zero change to business logic**. Business code depends only on the ports below, never on a broker SDK.

## 1. Ports (interfaces)

| Port | Responsibility |
|---|---|
| `MarketDataProvider` | Snapshot quotes, instrument lookup, trading sessions |
| `HistoricalDataProvider` | Bars and (where available) ticks for a range |
| `RealtimeDataProvider` | Subscribe / unsubscribe; async stream of canonical ticks, quotes, depth |
| `OrderflowProvider` | Trades with side, L2 depth updates, with a declared quality tier |
| `NewsProvider` | Timestamped headlines with entity tags and source |
| `CorporateActionProvider` | Splits, bonuses, dividends, mergers, symbol changes |
| `EventProvider` | Earnings, economic calendar, expiries, index rebalances |

A provider may implement any subset. It **declares what it implements** in a capability descriptor.

## 2. Capability descriptor

```
ProviderCapabilities
  id, version
  segments:        [NSE_EQ, NSE_FO, BSE_EQ, MCX, CRYPTO_PERP, ...]
  intervals:       {1m: max_bars_per_request=500, 1d: ...}
  history_depth:   {1m: "unknown", 1d: "10y"}
  depth_levels:    5 | 20 | 0
  aggressor_side:  exact | estimated | none
  max_subscriptions_per_socket
  rate_limits:     [ {endpoint, per_second, per_minute, per_hour} ]
  auth:            {kind, session_ttl}
  license:         {personal_use | redistributable}
```

The router chooses providers by capability, not by name. The UI shows the capability that produced a chart
(for example "NSE quote data, delta estimated").

## 3. Canonical models

All providers translate into these. Nothing else crosses the boundary.

| Model | Key fields |
|---|---|
| `Instrument` | `iid` (internal UUID), `canonical_symbol` (`NSE:EQ:RELIANCE`), `segment`, `isin`, `tick_size`, `lot_size`, `price_scale`, `currency`, `expiry`, `strike`, `option_type`, `status`, `valid_from`, `valid_to` |
| `ProviderInstrumentMap` | `iid`, `provider`, `provider_token`, `provider_symbol`, `verified_at` |
| `Bar` | `iid`, `interval`, `ts_open_utc`, `o,h,l,c`, `volume`, `oi`, `adjusted` (bool), `data_version`, `quality` |
| `Tick` | `iid`, `ts_exchange`, `ts_received`, `price`, `qty`, `side` (`buy/sell/unknown`), `side_method` |
| `Depth` | `iid`, `ts`, `bids[(px,qty,orders)]`, `asks[...]`, `levels` |
| `Quote` | last, bid, ask, volume, OI, prev close, `ts_exchange`, `ts_received` |

Rules: UTC internally, IST at display; prices as integer ticks or `Decimal`; never floats in storage keys.

## 4. Symbology and the instrument master

- `iid` is stable forever. Symbols change (renames, mergers); `iid` does not.
- Daily job loads each provider's instrument master (Angel's is a large daily JSON [V]), maps it to `iid`,
  and records changes (new, delisted, renamed, lot-size change).
- Provider tokens live only in `ProviderInstrumentMap`. Business code never sees them.

## 5. Price normalization and instrument verification (fixes Issue 1)

Reported symptom: a Rs 12,000 stock charted at 120, 400 or 4. I do not have your current code, so these are
**hypotheses to confirm** against it: wrong symbol resolution (different instrument with a similar name),
split-adjusted vs raw series mixed, unit scaling (paise vs rupees), a stray outlier bar stretching autoscale, or
index vs equity ticker collisions. The design removes the whole class of bug:

**Pipeline: nothing reaches a chart until it passes all gates**
1. **Resolve.** `canonical_symbol -> iid -> provider_token` from the verified map; ambiguous symbols are rejected.
2. **Verify identity.** Compare the provider's returned name/ISIN/segment with the master. Mismatch blocks the series.
3. **Scale check.** Compare the series' latest close with an independent anchor (last quote, prior EOD close from the
   NSE file). If the ratio is outside a tolerance band (say 0.5x to 2x) the series is quarantined, not drawn.
   Ratios near 10, 100, 1000 flag a unit-scale error explicitly.
4. **Tick-size check.** All prices must be multiples of `tick_size` (within epsilon).
5. **Outlier guard.** Bars where `high/low` or `close/prev_close` exceed segment limits (circuit-based bands) are
   flagged; flagged bars are shown, never silently dropped.
6. **Adjustment consistency.** One series is either fully adjusted or fully raw; the adjustment factor table
   (from `CorporateActionProvider`) is applied by us, once, and the flag is stored.
7. **Chart contract.** The chart receives `{series, price_scale, tick_size, last_verified_price, quality}` and
   fixes the visible price range from validated data. A badge shows `NSE:EQ:RELIANCE | tick 0.05 | last verified 1,234.50`.

**Acceptance tests:** a golden set of stocks including high-priced names (Rs 10,000+), recently split names, and
indices; each must chart within 0.5% of the independent anchor.

## 6. Rate-limit governor

One governor per provider. Token buckets per endpoint, seeded from the capability descriptor. Example for
Angel (2024 forum table, **re-verify before use** [V]): candle data 3/s, 180/min, 5000/hour; quote 10/s, 500/min,
5000/hour. Rules: requests queue rather than fail; backfills are low priority; live-view requests pre-empt them;
429 responses trigger exponential backoff with jitter and a global pause.

## 7. Feed Health Engine (fixes Issue 2: "connect feeder")

```
CONNECTING -> AUTHENTICATED -> SUBSCRIBED -> LIVE
      ^             |              |          |
      |             v              v          v
      +--------- RECONNECTING <--- STALE <----+
                        |
                        v
                  FAILED_OVER (secondary provider) -> DEGRADED -> FAILED
```

- **Heartbeat.** Send provider pings per its protocol; track last-message time per connection.
- **Staleness is session-aware.** A symbol is stale if no tick for `N` seconds *during its trading session*
  (N depends on liquidity tier); outside session it is `CLOSED`, not `STALE`.
- **Auto-reconnect.** Exponential backoff with jitter (for example 1s, 2s, 4s ... capped at 60s), refresh the
  session token if the failure is auth-related (Angel sessions expire daily [V], so a scheduled pre-market login
  is required), then resubscribe from the desired-state set, never from memory of what was sent.
- **Gap repair.** After reconnect, request the missed bar range from the historical port and merge idempotently.
- **Failover.** Ordered provider list per segment; promote the secondary when the primary is `FAILED` or its
  latency exceeds a threshold; fail back only after a stable period (prevents flapping). Data from a fallback
  provider is labelled with its own quality tier.
- **Latency tracking.** `ts_received - ts_exchange` per tick, p50/p95/p99 per provider and segment; also
  inter-arrival time and drop estimates.
- **Subscription budgeting.** Respect the per-socket token limit (about 1000 cited by Angel staff [V]); shard
  across sockets and prioritise watched symbols over background scans.
- **Status dashboard.** Per provider and segment: state, last tick age, latency percentiles, reconnect count,
  subscription count, and a plain-language message ("Angel feed reconnecting, retry in 8s"). The UI never shows a
  bare "connect feeder": it shows *why*, *since when* and *what the system is doing about it*.
- **Alerts.** Prometheus metrics; page on sustained `FAILED` during market hours.

## 8. Provider specifics

### Angel One adapter
- Login: client code + PIN + TOTP (**PIN is required in addition to the key, client id and TOTP secret you listed**).
- Pre-market scripted login; refresh token handling; feed token for the WebSocket.
- Historical: chunk requests to the 500-record cap; honour the governor; cache raw responses to Parquet.
- Order APIs are **not implemented** in this product, which keeps us outside the static-IP order rules [V that
  those rules concern order execution; confirm read-only status with Angel].
- Depth-20 is treated as beta; the adapter reports `depth_levels` honestly and the engine degrades gracefully.

### Delta Exchange adapter
- HMAC-SHA256 signing; clock sync is mandatory because signatures are valid only 5 seconds [V].
- Whitelisted IP is needed for trading-permission keys; use read-only data keys where the platform allows [verify].
- Budget the 20,000 weight per 5 minutes across market-data calls (weight 3 each) [V].
- True L2 and trades channels make this the first provider that can deliver `aggressor_side = exact`.
- Forex: not confirmed in docs read; keep the `forex` segment behind a separate provider decision.

## 9. Migrating off yfinance (strangler pattern)

1. **Introduce the ports** and wrap yfinance as `YFinanceProvider` implementing them (no behaviour change).
2. **Build `AngelProvider`** against the same ports with the instrument master and normalization pipeline.
3. **Shadow mode.** Run both for the same symbols; compare closes, volumes and bar timestamps; log differences.
4. **Parity report.** Acceptable tolerance: price within one tick on closed bars; volume differences explained
   (exchange vs consolidated).
5. **Cut over per segment** (equity first, then index, then MCX), behind a feature flag with instant rollback.
6. **Remove yfinance** after one full month of clean parity, including expiry week and a corporate action.
7. Keep `SyntheticProvider` permanently for tests and demos.

Note: the MCX "proxy" mappings in the current scanner (COMEX gold, WTI and so on) disappear once Angel's MCX
segment [V, MCX covered] is connected; the UI must stop showing the proxy tag at that point.

## 10. Checklist for adding a future provider
1. Implement the needed ports; fill the capability descriptor.
2. Write the instrument-master loader and `ProviderInstrumentMap`.
3. Pass the **provider contract test suite** (shared tests every provider must pass: canonical models, UTC
   timestamps, tick-size validity, reconnect, rate-limit adherence, error mapping).
4. Register in the provider registry by configuration. No other file changes.
