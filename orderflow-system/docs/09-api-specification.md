# 09 · API Specification (FastAPI; OpenAPI at `/docs`)

Auth: header `x-api-key` when `OFX_API_KEY` is set (constant-time compare); `/health` always open. CORS origins from `OFX_CORS_ORIGINS`. All times ISO-8601 **with UTC offset** (naive → 400). Max span 2 days. Errors: 400 `{error}` (domain validation), 401, 422 (schema).

| Method & path | Query | Response |
|---|---|---|
| GET `/health` | — | `{status:"ok"}` |
| GET `/api/v1/capabilities` | — | provider capability record + `trade_quality` |
| GET `/api/v1/footprint` | `iid, tick(>0), start, end, tf(1m,5m,15m,30m,1h), ratio(1.1–20), session(NSE\|MCX\|CRYPTO, optional)` | `{provider, data_quality, bars:[{ts_open, ts_close, tick, open, high, low, close, volume, delta, delta_min, delta_max, cvd_open, cvd_close, poc_row, unknown_share, quality, rows:{row:[bid,ask]}, imbalances:[{row,side}], stacked:[{side,low_row,high_row}]}]}` |
| GET `/api/v1/volume-profile` | `iid, tick, start, end` | `{approximated, tick, rows, levels:{poc,vah,val,…}, nodes:[{kind,row,price,volume,prominence_share}]}` or `{empty:true}` |
| GET `/api/v1/market-profile` | `iid, tick, start, end, session(NSE\|MCX\|CRYPTO), period(5–60)` | `{profiles:[{start, counts, letters, levels}], note}` |
| GET `/api/v1/observations` | `iid, tick, start, end, tf, session(optional)` | `{provider, observations:[Observation.to_dict()]}` |
| GET `/api/v1/heatmap` | `iid, tick, start, end, dt(0–3600 s), scale(linear\|log\|percentile), mode(max\|avg)` | `{provider, depth_levels, t_start, dt_seconds, row_lo, tick, shape:[rows,cols], intensity:[[0..1]], note}`; span ≤ 6 h and ≤ 200k cells, else 400 |
| GET `/api/v1/export/footprint` | same as footprint + `format=csv\|json\|parquet` | CSV rows `ts_open,row,price,bid_vol,ask_vol,delta,bar_quality`, the JSON payload, or Parquet with the same columns (timestamp[us,UTC], int64 row, float64 price/volumes, string quality; zstd). Parquet needs the optional `parquet` extra (`pip install pyarrow`); without it the API returns 501 |
| POST `/api/v1/scenarios` | query as observations; JSON rule body (doc 08) | `{rule, observations_considered, matches:[{summary, teaching_note, confidence, data_quality, evidence, limitations}]}`; invalid rule → 400 |
| GET `/api/v1/scenarios/examples` | — | `{rules:[...]}` |
| WS `/ws/v1/stream` | `topic`, `x_api_key` (if enabled) | JSON messages; `dropped` counter after backpressure; close 4401 on bad key |

Row → price: `price = row × tick`. Observation fields: `kind, ts_start, ts_end, price_low, price_high, summary, evidence, data_quality, method, confidence, alternative_readings, limitations, teaching_ref`.
**Rate limit:** token bucket per client IP, `OFX_RATE_PER_MIN` (default 120, 0 disables), 429 + `Retry-After`; `X-Forwarded-For` is trusted only when `OFX_TRUST_PROXY=1`. `/health` is exempt.
**Live ingest:** set `OFX_LIVE_IID` (+ `OFX_LIVE_TICK`, `OFX_LIVE_TF`) to stream a provider into topic `<iid>:footprint`; messages `{type:"footprint", closed:bool, bar}`. Providers without an aggressor flag pass through a streaming tick rule (first print stays unknown).
**Forward recording:** with `OFX_LIVE_IID` and `OFX_DATABASE_URL` set, live trades are batched into `trades` (idempotent) and each closed bar is stored once; the recorded stream becomes the history (Angel offers none).
**Additions for the chart UI.** `GET /api/v1/instruments` lists instruments (`tick_size`, `lot_size`, `tz`, `session`, `row_hint`). `GET /api/v1/session-profiles` returns one volume profile per exchange session with `rows: {row: [bid, ask]}`, `levels` (POC/VAH/VAL) and HVN/LVN nodes. Footprint bars now also carry `bid_volume`, `ask_volume` and `vwap` (session-reset, at the bar's close); `/market-profile` adds `tick`, `period_minutes`, `n_periods`, `open`, `close`, `ib_high_row`, `ib_low_row`. Footprint responses are rejected with 400 above 150,000 bar-by-row cells (use a larger row size). Closed windows are cached in memory for `OFX_CACHE_TTL` seconds (default 120, 0 disables); a window that has not closed is never cached. Max span is now 7 days.

**Demo market.** For `SYN:NIFTY` and `SYN:CRUDE` the synthetic provider generates deterministic, session-shaped trades (any query window is an exact slice of the same path). Calibration targets are documented in `providers/demo_market.py`; it is **not** market data and the UI labels it DEMO DATA.

**Pagination.** `/footprint` and `/observations` accept optional `limit` (1–2000) and `cursor`. Responses add `next_cursor` (null on the last page) and `total_bars` / `total`. The cursor is the ISO timestamp of the first item of the next page (keyset, not offset), compared as an instant. CVD and detectors are computed over the whole requested range and then sliced, so paged results concatenate to exactly the unpaged result. Omitting both parameters returns everything (backwards compatible); bad values return 400/422. Decision: keyset over offset because pages stay stable as new data arrives and no offset arithmetic is needed.

**Not yet built [gap]:** a real depth source for the heatmap (only the synthetic provider supplies depth history); live Angel websocket wiring; Delta adapter.

**Session alignment:** when `session` is given, time bars start at that session's open (NSE 09:15 IST, MCX 09:00 IST) so 30-minute and hourly bars match exchange charts, and CVD resets per exchange session. Without it, bars align to UTC and CVD resets at UTC midnight (right for 24/7 crypto, wrong for NSE/MCX). Live ingest honours it via `OFX_LIVE_SESSION` (NSE|MCX|CRYPTO); unset means UTC.
**WebSocket auth:** send `x-api-key` as a header where the client allows it; browsers cannot, so the `x_api_key` query parameter also works but can appear in URL logs — use TLS and rotate the key if logs are shared.
