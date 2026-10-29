# Order Flow Charting System

Backend (Python 3.13, FastAPI) · Frontend (React + TypeScript, custom canvas chart engine) · PostgreSQL/TimescaleDB schema · 10 design documents in `docs/`.

## Run (no credentials needed; synthetic data)
```
cd backend && pip install -r requirements.txt pytest ruff mypy pglast && python -m pytest -q
uvicorn ofx.main:app --reload
cd frontend && npm install && npm test && npm run build && npm run dev
```
UI smoke test (needs both servers running): `pip install playwright && python scripts/ui_smoke.py`.
Database tests: `OFX_TEST_DSN="host=... dbname=..." python -m pytest tests/test_storage.py`.
Full stack: copy `.env.example` to `.env`, fill it locally, then `docker compose up --build`.

## Status
| Area | State |
|---|---|
| Footprint, delta/CVD, imbalance, volume profile, TPO, DOM, heatmap, 6 detectors | built, unit-tested |
| REST API, WebSocket hub, rate limit, API key | built, tested |
| Live ingest (provider → bars → WebSocket) | built, tested with fake/synthetic feeds |
| PostgreSQL store + replay | built, tested on real PostgreSQL 16 |
| Forward recorder, CSV/JSON/Parquet export, keyset pagination, CVD pane, heatmap canvas, profile layout | built, tested |
| Replay of detectors over recorded data (`scripts/replay.py`), no-repaint test | built, tested |
| Market Profile (TPO) panel | built, layout tested |
| Scenario rules as validated JSON + evaluator + endpoint | built, tested |
| Chart UI (custom canvas engine): numeric bid x ask footprint with auto row size, imbalance and POC marking, bar statistics table, delta bars, buy/sell volume profile, session VWAP, candles + session volume profiles, TPO letters with value area / IB / single prints, crosshair + cell tooltip, pan/zoom, 1/2/4-chart layouts | built; pure maths unit-tested (34 tests); rendered and inspected in Chromium; `scripts/ui_smoke.py` guards against blank charts |
| Demo market (`SYN:NIFTY`, `SYN:CRUDE`): NSE/MCX-shaped sessions, realistic price/tick/volume scale, deterministic per day | built, tested. **Generated, not market data**; the UI shows a DEMO DATA badge |
| TimescaleDB hypertables | written, **not executed** |
| Angel One REST (login/TOTP/candles) | built, tested on **mocked** responses only |
| Delta Exchange public data (products, candles, recent trades, trade parsing) | built, tested on **mocked** responses only |
| Angel live ticks (SDK bridge + tick→trade conversion) | conversion tested; SDK bridge **untested live** |
| Delta depth stream (`l2_orderbook`) | parser tested on mocked payload; socket **untested live** |

Live check (read-only, run on your machine; the build sandbox cannot reach the exchanges): `cd backend && python scripts/smoke_live.py`

Output is observational only: no BUY/SELL/HOLD. Credentials are read from the environment by name; never commit `.env`.
