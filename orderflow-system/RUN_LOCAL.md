# Run locally (your machine)

**Windows shortcut:** after `git pull` and filling `backend\.env`, double-click `start-angel.bat` (stocks/NIFTY), `start-delta.bat` (crypto; add `DELTA_TAKER_VERIFIED=1` to `backend\.env` only after reviewing the smoke output) or `start-demo.bat`. It opens the API and UI windows and the browser. Leave both windows open. Set `OFX_API_KEY=` (blank) in `backend\.env` for local use. The steps below are the manual equivalent.

Needs Python 3.11+ and Node 18+. Commands use a terminal; on Windows use PowerShell and replace `source .venv/bin/activate` with `.venv\Scripts\Activate.ps1`.

## 1. Get the code
```
git pull            # or: git clone https://github.com/ManishPatil2005/funzip && cd funzip/orderflow-system
```

## 2. Backend setup
```
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-live.txt
cp ../.env.example .env          # Windows: copy ..\.env.example .env
```
Edit `backend/.env` (git-ignored; never paste its values into chat or commit it).

## 3. Smoke test the live connections (read-only)
```
python scripts/smoke_live.py --angel-token 3045 --angel-exch NSE
```
It only logs in to Angel, requests one candle series, and reads Delta's public products and recent trades. It places no orders and prints no secrets. Paste the output back if anything says FAILED, or to confirm payload shapes.

## 4. Start the API with a real provider
Pick one in `backend/.env` (or as environment variables):

| Goal | Settings |
| --- | --- |
| Demo data (default) | `OFX_PROVIDER=synthetic` |
| Delta crypto (public data, no keys needed) | `OFX_PROVIDER=delta` and `OFX_INSTRUMENTS=BTCUSD,ETHUSD` |
| Angel One stocks | `OFX_PROVIDER=angel`, the four `ANGEL_*` values, and `ANGEL_TOKENS=NSE:SBIN-EQ=NSE:3045` (`iid=EXCHANGE:symboltoken`, comma separated) |

```
uvicorn ofx.main:app --port 8000
```
Check: open http://127.0.0.1:8000/api/v1/instruments. The chart shows a **DEMO DATA** badge only for generated data.

What each provider gives you:
- **Delta**: recent public trades only (no deep history). Delta's taker side is unverified; delta shows as ESTIMATED until the smoke test confirms `buyer_role`/`seller_role` and you set `DELTA_TAKER_VERIFIED=1`.
- **Angel**: candles only; it has no historical ticks. Footprints need ticks **recorded forward**: set `OFX_DATABASE_URL`, `OFX_LIVE_IID`, `OFX_LIVE_TICK`, `OFX_LIVE_TF`, `OFX_LIVE_SESSION=NSE` and leave the API running during market hours. The live path is built but has not run against a real Angel session.

## 5. Frontend
```
cd ../frontend
npm ci
npm run dev
```
Open http://localhost:5173. The dev server proxies `/api` and `/ws` to port 8000.

## 6. Optional: database
`docker compose up` needs a `.env` at `orderflow-system/` with `POSTGRES_PASSWORD`. The compose file starts Postgres/TimescaleDB, Redis and the API only (no frontend service). Migration 0002 (Timescale) is unverified, and it deletes `trades` older than 90 days; change that before recording ticks you want to keep.

## Troubleshooting
- `FAILED: AngelAuthError`: wrong client id, PIN or TOTP secret, or the system clock is off by more than 30 s.
- Empty chart on Delta: widen the range or switch to 5D; only recent trades exist.
- Anything else: paste the exact error text (secrets are never printed).
