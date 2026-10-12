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
| GET `/api/v1/export/footprint` | same as footprint + `format=csv\|json` | CSV rows `ts_open,row,price,bid_vol,ask_vol,delta,bar_quality` or the JSON payload |
| POST `/api/v1/scenarios` | query as observations; JSON rule body (doc 08) | `{rule, observations_considered, matches:[{summary, teaching_note, confidence, data_quality, evidence, limitations}]}`; invalid rule → 400 |
| GET `/api/v1/scenarios/examples` | — | `{rules:[...]}` |
| WS `/ws/v1/stream` | `topic`, `x_api_key` (if enabled) | JSON messages; `dropped` counter after backpressure; close 4401 on bad key |

Row → price: `price = row × tick`. Observation fields: `kind, ts_start, ts_end, price_low, price_high, summary, evidence, data_quality, method, confidence, alternative_readings, limitations, teaching_ref`.
**Rate limit:** token bucket per client IP, `OFX_RATE_PER_MIN` (default 120, 0 disables), 429 + `Retry-After`; `X-Forwarded-For` is trusted only when `OFX_TRUST_PROXY=1`. `/health` is exempt.
**Live ingest:** set `OFX_LIVE_IID` (+ `OFX_LIVE_TICK`, `OFX_LIVE_TF`) to stream a provider into topic `<iid>:footprint`; messages `{type:"footprint", closed:bool, bar}`. Providers without an aggressor flag pass through a streaming tick rule (first print stays unknown).
**Forward recording:** with `OFX_LIVE_IID` and `OFX_DATABASE_URL` set, live trades are batched into `trades` (idempotent) and each closed bar is stored once; the recorded stream becomes the history (Angel offers none).
**Not yet built [gap]:** pagination; a real depth source for the heatmap (only the synthetic provider supplies depth history); live Angel websocket wiring; Delta adapter.

**Session alignment:** when `session` is given, time bars start at that session's open (NSE 09:15 IST, MCX 09:00 IST) so 30-minute and hourly bars match exchange charts, and CVD resets per exchange session. Without it, bars align to UTC and CVD resets at UTC midnight (right for 24/7 crypto, wrong for NSE/MCX). Live ingest currently uses the UTC default [gap].
**WebSocket auth:** send `x-api-key` as a header where the client allows it; browsers cannot, so the `x_api_key` query parameter also works but can appear in URL logs — use TLS and rotate the key if logs are shared.
