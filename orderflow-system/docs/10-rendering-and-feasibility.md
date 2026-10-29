# 10 · Rendering Specification (Phase 4) and Data-Source Feasibility (Phase 7)

## A. Rendering
**Engine.** One `<canvas>` per pane, drawn by pure functions in `src/render/*` from a `SceneInput`; no charting library. Bars are laid out by **index**, not clock time, so overnight and weekend gaps collapse (session boundaries are marked with a dashed line and a date label). Coordinates: `idxToX`/`priceToY` in `lib/viewport.ts` (inverse pairs, unit-tested). Panes stack main, bar statistics, delta bars, time axis and share one x-range; the right gutter is the price axis. In short panes the delta pane is dropped first, then the stats table, so footprint numbers stay legible (`render/layout.ts`).

**Readable footprint.** Numbers are drawn only when the row is >= 10px tall and the half-bar is wide enough for the text. The row size is chosen automatically: the smallest "nice" multiple of the tick whose rows are at least 16px tall for the visible price span (`pickRowSize`), then the bars are re-fetched at that size (debounced 350ms; never driven by the placeholder range before data arrives). The user can pin a row size. Imbalance cells are filled and outlined; stacked runs get a heavier outline; POC is a yellow row outline; running-delta extremes are labelled as such (not as vendor-specific terms).

**Modes.** Footprint (stats table, delta bars, visible-range profile split by ask/bid, VWAP), Candles + VP (per-session volume profiles with POC/VAH/VAL, buy/sell volume bars, VWAP), TPO (letter per 30-minute period, POC row, value-area band, initial balance, single prints). Delta bars are candles of session-reset CVD; wicks are the running-delta extremes inside the bar. Session VWAP resets with the session and is drawn per session, never connected across the gap.

**Interaction.** Wheel zooms time around the cursor; Ctrl/Cmd+wheel or wheel over the price axis zooms price; drag pans (vertical drag leaves auto-scale); double-click resets (on the axis: back to auto-scale); hover shows a crosshair, OHLC/Vol/Buy/Sell/delta legend and a per-cell tooltip.

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
A1 Delta signature = HMAC-SHA256(secret, method+timestamp+path+query+body). A2 5-second timestamp window. A3 Trade payload may or may not include taker side. A4 Angel 20-level depth is beta and subject to the token cap. A5 NSE/MCX session hours as configured in `SessionSpec`. A6 Retention periods are defaults. A7 Detector thresholds are starting values, not validated edges. A8 Vendor defaults in doc 01 marked [U] are unconfirmed. A9 Angel REST paths, headers and candle payload shape follow public docs as I know them and are tested only against mocked responses; the first real login may need adjustment. A10 Angel live websocket is not wired. A11 0002_timescale.sql has not been executed. A12 Delta public endpoints (`/v2/products`, `/v2/history/candles`, `/v2/trades/{symbol}`) and `buyer_role`/`seller_role` fields follow public docs as I know them; unverified until `scripts/smoke_live.py` is run. Delta public trades give only RECENT history, so footprint history must be recorded forward.

## D. Credentials
No credential values are requested or accepted in chat. Set names only, in a local `.env`/secrets manager: `ANGEL_SMARTAPI_KEY, ANGEL_CLIENT_ID, ANGEL_PIN, ANGEL_TOTP_SECRET, DELTA_EXCHANGE_API_KEY, DELTA_EXCHANGE_SECRET`. Adapters are skeletons (no network I/O) until you confirm stock integration, then Delta. A13 The demo market's volatility, volume and delta-price relationship are calibrated to look like index/commodity futures, not fitted to any real day; it must never be used to judge a detector or a rule. A14 The UI is verified by pure-function tests, headless-Chromium screenshots reviewed by eye, and `scripts/ui_smoke.py` (non-blank checks); there is no pixel-diff regression suite. A15 Not profiled with several thousand bars on screen; the 150,000-cell response cap bounds the work for now.
