# Market Scanner

A FastAPI application for NSE and MCX market scanning with a rule-based strategy builder and a
Market Profile (TPO) engine following Jim Dalton's auction-market concepts.

- **Scanner**: 18 built-in strategies across NIFTY 50, NSE indices, MCX proxies, or any NSE symbol (`NSE:IRCTC`).
- **Strategy Builder**: combine 24 indicators and price fields into buy/sell rules; saved to SQLite.
- **Market Profile**: TPO letters, POC, 70% value area, initial balance, open and day types, shapes, excess and poor
  highs/lows, single prints, naked POCs, the 80% rule, and a scored BUY / SELL / NEUTRAL bias with entry, stop and targets.
- **Security**: API-key auth, rate limits, strict CSP, validated inputs, no `eval`, non-root read-only container.

> Educational analysis, not investment advice. Output is heuristic and can be wrong. Verify prices with your broker.

## Quick start (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
SCANNER_DATA_PROVIDER=synthetic uvicorn app.main:app --reload   # offline demo data
uvicorn app.main:app --reload                                    # live data via yfinance
pytest -q
```

Open http://localhost:8000. With no `SCANNER_API_KEYS` set, authentication is disabled in development only.

## Production deployment (Docker Compose + nginx + TLS)

1. `cp .env.example .env`; set `SCANNER_API_KEYS` (`python -c "import secrets; print(secrets.token_urlsafe(48))"`)
   and `SCANNER_DOMAIN`.
2. Put the same domain in `deploy/nginx.conf` (`server_name`).
3. Obtain a certificate (for example `certbot certonly --standalone -d your.domain`) and copy `fullchain.pem` and
   `privkey.pem` into `deploy/certs/`.
4. `docker compose up -d --build`
5. Open `https://your.domain`, enter the API key at the top right (kept in `sessionStorage`, cleared when the tab closes).

The app refuses to start in production without a key of at least 32 characters, with a wildcard host list, or with
the synthetic provider.

**Other options**: any container host (Fly.io, Render, Cloud Run, a VPS) works with the same image; set the same
environment variables, keep `SCANNER_TRUST_PROXY=true` only when a trusted proxy overwrites `X-Forwarded-For`, and let
the platform terminate TLS. Caddy can replace nginx for automatic certificates (`reverse_proxy app:8000`).

## Security model

| Control | Where |
|---|---|
| API key, constant-time compare, multiple keys for rotation | `core/security.py` |
| Per-IP rate limits (global and `/api/scan`), plus nginx `limit_req` | middleware, `deploy/nginx.conf` |
| Request body cap (64 KB), host-header allow-list, no wildcard in production | middleware, `core/config.py` |
| CSP (`script-src 'self'`), frame denial, nosniff, no-referrer, HSTS, `no-store` on API | `SecurityHeadersMiddleware` |
| Custom strategies are validated JSON run by a fixed interpreter; names, periods and condition counts are bounded | `strategies/builder.py` |
| Symbols validated by regex and allow-list; parameterised SQL only; DOM built with `textContent` | routes, `db.py`, JS |
| Docs/OpenAPI disabled in production; errors never leak stack traces | `main.py` |
| Non-root, read-only filesystem, all capabilities dropped, memory and PID limits | `Dockerfile`, compose |
| CI: pytest, bandit, pip-audit | `.github/workflows/ci.yml` |

Limits to know about: rate limits and the data cache are per process (2 workers by default). For several replicas,
move them to Redis. The single shared API key means one trust domain; add per-user auth before exposing it to others.

## Built-in strategies

Trend: EMA crossover, golden/death cross, MACD cross, Supertrend flip, ADX + DI cross.
Breakout: Donchian (Turtle), 52-week high/low, volume breakout, Bollinger squeeze, inside bar, NR7.
Mean reversion: RSI reversal, Bollinger reversion, Stochastic cross.
Price action: engulfing and hammer/star candles, opening gap.
Intraday (5m/15m): VWAP reclaim/loss, opening range breakout.
Every parameter is editable in the scanner UI.

## Market Profile rules (Dalton)

| Concept | Implementation |
|---|---|
| TPO periods | 30-minute letters A–Z then a–z; NSE 09:15–15:30 IST, MCX 09:00–23:30 IST |
| POC | Row with the most TPOs; ties go to the row nearest the profile midpoint |
| Value area | 70% of TPOs, expanded from the POC two rows at a time toward the heavier side |
| Initial balance | First two periods; extension up/down measured against IB range |
| Open types | Open-Drive, Open-Test-Drive, Open-Rejection-Reverse, Open-Auction (in or out of prior range) |
| Day types | Normal, Normal Variation, Trend, Double Distribution, Neutral, Neutral Extreme, Non-Trend |
| Shapes | P, b, D, B, elongated |
| Structure | Excess (tail of 2 or more single-print rows) vs poor high/low; interior single prints; naked POCs |
| Multi-day | Value relationship (higher, overlapping, inside, outside, lower), open location, 80% rule |
| Bias | Additive score; BUY at +3 or more, SELL at −3 or less; every point is listed with its reason |

Dalton's day types are discretionary, so the classifiers are documented heuristics. Their thresholds are constants at
the top of `app/profile/market_profile.py`; tune them against your own observations.

## Data caveats

- yfinance is an unofficial Yahoo Finance wrapper: delayed, rate-limited, and subject to Yahoo's terms (personal use).
  Intraday history is capped (1m: 7 days; 5m/15m/30m: 60 days).
- **MCX is not on Yahoo.** MCX symbols map to global futures proxies (COMEX gold, silver, copper, WTI crude, natural gas),
  priced in USD with different contract specifications and trading hours. Treat them as directional proxies only.
- NIFTY 50 membership changes; the list in `app/data/universe.py` is a snapshot. Symbols that fail to load are reported
  per row rather than failing the scan.
- For real NSE/MCX data, implement `DataProvider.history()` against a broker API (Zerodha Kite, Angel One SmartAPI,
  Upstox, Dhan) and register it in `app/data/provider.py`. Redistributing exchange data commercially needs a licence.

## Layout

```
app/core        config, security middleware, logging
app/data        universes, yfinance + synthetic providers, TTL cache
app/strategies  indicators, built-ins, rule builder, scanner
app/profile     Market Profile engine
app/api         REST routes          app/static, app/templates   UI
deploy/         nginx.conf           tests/   pytest suite (53 tests)
```
