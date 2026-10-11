# Project Memory

Read this first in every session. Update at the end of every session. Last updated: 2026-10-10.

## Owner and context
- Owner: Manish, 3rd-year B.Tech CSE student building trading systems for Indian markets. Prefers formal tone and
  concise, structured output; likes being offered options.
- Existing stack: Python, FastAPI, SQLite, Jinja2.

## Current state
- **Phase 0 (research and blueprint): complete, awaiting owner review.** No new application code written in this
  phase, per the brief.
- **Delivered earlier (v1 scanner, folder `stock-scanner`, zip sent):** FastAPI scanner with 18 strategies, rule
  builder, Market Profile (Dalton) engine, API-key auth, rate limits, Docker/nginx deployment, 53 passing tests.
  It uses yfinance (blocked in the build sandbox, so never run against live data) and outputs BUY/SELL/NEUTRAL,
  which the new brief forbids (ADR-007).
- Owner's reported issues in the **current system** (code not shared with me): chart price scaling errors,
  "connect feeder" disconnects, need for historical scanner exports, need for advanced backtesting.

## Key facts learned (see RESEARCH.md for sources)
- Angel SmartAPI login needs client code + **PIN** + TOTP; sessions expire daily; WebSocket modes LTP/Quote/Snap/
  Depth-20 (beta); about 1000 tokens per socket; candle API returns at most 500 records per request; candle rate
  limit 3/s, 180/min, 5000/hour (2024 table).
- SEBI static-IP rules (effective 2026-04-01) apply to **order execution**; read-only data status unconfirmed.
- Delta Exchange India: HMAC-SHA256 signature valid 5 s; 20,000 weight per 5 minutes; L2, trades, candles
  channels; forex not seen in docs.
- NSE true aggressor-side data is not available to retail APIs; NSE redistribution needs licensing.

## Open questions for the owner
1. Approve or change ADR-004 (defer Kafka/Kubernetes) and the other Proposed ADRs.
2. Personal/self-hosted first, SaaS later: confirm.
3. Share the current repository so Issues 1 to 4 can be diagnosed from real code.
4. Forex source preference.
5. Budget for historical intraday data, if any.

## Credentials protocol
Variables expected later: `ANGEL_SMARTAPI_KEY`, `ANGEL_CLIENT_ID`, `ANGEL_TOTP_SECRET`, plus **`ANGEL_PIN`**
(required, not in the original list). Delta later: `DELTA_EXCHANGE_API_KEY`, `DELTA_EXCHANGE_SECRET`. Request
them only after the stock integration plan is approved, and **never accept values in chat**; the owner places
them in a local env file or secrets manager.

## Conventions
Canonical symbol `SEGMENT:TYPE:SYMBOL`; UTC internally; evidence tags [V]/[A]/[U]; language policy in RULES.md.

## Document map
RESEARCH, PRD, ARCHITECTURE, DESIGN, RULES, SECURITY, TEST_PLAN, DECISIONS, DATABASE_SCHEMA,
DATA_PROVIDER_LAYER, ORDERFLOW_ENGINE, SCANNER_ENGINE, BACKTEST_ENGINE, LEARNING_ENGINE, AI_ARCHITECTURE,
ROADMAP, STARTUP_STRATEGY, PHASE0_REPORT.
