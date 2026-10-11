# 10 · Rendering Specification (Phase 4) and Data-Source Feasibility (Phase 7)

## A. Rendering
**Layering.** Lightweight Charts 4.2 draws candles/axes; a transparent `<canvas>` (`FootprintLayer`) is stacked on top, `pointer-events:none`, and repainted via `requestAnimationFrame` on `subscribeVisibleLogicalRangeChange`. Mapping: x = `timeScale.timeToCoordinate(t)`, y = `series.priceToCoordinate(p)` (all mapping goes through the chart so pan/zoom stay in sync). DPR scaling via `setTransform`.

**Footprint cell** (per bar column, width = barSpacing − 2 px):
```
 |  bid |  ask |      cell fill  = colorAt(volume / maxVolumeOnScreen)  (alpha .55)
 |   12 |  31  |      yellow outline = POC row   green/red outline = stacked imbalance (ask / bid)
 |   40 |  96  |      numbers drawn only if cell h ≥ 11 px and w ≥ 46 px (else colour only)
```
**Heatmap** columns = time buckets, rows = price rows; intensity as doc 07; colour ramp = backend stops (dark blue → red). **Volume profile**: horizontal bars anchored at the right edge, width ∝ volume, POC/VAH/VAL lines. **TPO**: monospace letters per row, IB bracket. **CVD pane**: line of `cvd_close` with session-reset breaks. **Quality badge** (EXACT/ESTIMATED/BAR_APPROXIMATED) always visible beside the chart title.
**Performance:** only visible bars drawn; text culled by size; one pass per frame. **Known gap [U]:** not profiled with thousands of bars; WebGL/offscreen canvas is the next step if needed.

## B. Phase 7 — Can each source support each feature?
| Feature | Angel One (NSE/MCX) | Delta Exchange (crypto) |
|---|---|---|
| Real-time trades | Snapshot ticks (≈1 s) — **partial** | Trades channel — yes |
| Exact aggressor side | **No** (estimate) | **[U]** only if payload has taker side |
| Footprint / delta / CVD / imbalance | **Estimated** | Exact if A3 verified, else estimated |
| Volume profile | From ticks (volume exact, split estimated) or candles (**bar-approximated**) | Yes |
| TPO / Market Profile | **Fully implementable** (candles) | Fully implementable |
| DOM | 5 levels (20-level beta) | up to 20 levels |
| Heatmap | Coarse | Moderate |
| Iceberg / spoof | Not reliable | Pattern-only |
| Historical ticks | **None** → backtests of delta impossible; forward-record from today | Limited [U] |
| Missing data / limits | ~500 candles per request; ~1000 tokens per connection; session/TOTP re-login; April-2026 access changes | weight limit ≈20,000 / 5 min; signature clock skew ≈5 s |

## C. Assumptions register (all unverified until tested with real keys)
A1 Delta signature = HMAC-SHA256(secret, method+timestamp+path+query+body). A2 5-second timestamp window. A3 Trade payload may or may not include taker side. A4 Angel 20-level depth is beta and subject to the token cap. A5 NSE/MCX session hours as configured in `SessionSpec`. A6 Retention periods are defaults. A7 Detector thresholds are starting values, not validated edges. A8 Vendor defaults in doc 01 marked [U] are unconfirmed. A9 Angel REST paths, headers and candle payload shape follow public docs as I know them and are tested only against mocked responses; the first real login may need adjustment. A10 Angel live websocket is not wired. A11 0002_timescale.sql has not been executed.

## D. Credentials
No credential values are requested or accepted in chat. Set names only, in a local `.env`/secrets manager: `ANGEL_SMARTAPI_KEY, ANGEL_CLIENT_ID, ANGEL_PIN, ANGEL_TOTP_SECRET, DELTA_EXCHANGE_API_KEY, DELTA_EXCHANGE_SECRET`. Adapters are skeletons (no network I/O) until you confirm stock integration, then Delta.
