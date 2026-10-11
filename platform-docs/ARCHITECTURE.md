# Architecture

Status: proposed, pending your approval of the deviations listed in DECISIONS.md (notably ADR-004: Kafka and
Kubernetes are deferred, not dropped).

## 1. Shape of the system

A **modular monolith** with hard internal boundaries (ports and adapters), deployable as one container at first and
splittable along the same seams later.

```
                  Next.js + TypeScript + Tailwind + Lightweight Charts (custom canvas layers)
                                        |  HTTPS / WebSocket
                              Cloudflare (WAF, DDoS, TLS)
                                        |
                +-----------------------+------------------------+
                |                    FastAPI API                  |
                |  REST  |  Realtime gateway (WS)  |  Auth/RBAC  |
                +--+---------+-----------+-----------+-----------+
                   |         |           |           |
          Scanner    Backtest    Profile/Orderflow   Learning     AI service
          engine     engine      engines             engine       (NL -> logic graph)
                   \         |           |           /
                    +------- Analytics core (Polars, DuckDB, Arrow) -------+
                                        |
        +-------------------------------+--------------------------------+
        | Redis: latest quotes, pub/sub, rate-limit buckets, job queue   |
        | PostgreSQL + TimescaleDB: metadata, bars, short-lived ticks    |
        | Object storage (Parquet): cold history, exports, backtest data |
        +-------------------------------+--------------------------------+
                                        |
                    Ingestion workers (feed manager, backfill, EOD loader)
                                        |
                       Provider ports -> Angel | Delta | NSE EOD | future
```

## 2. Components

| Component | Responsibility | Notes |
|---|---|---|
| Provider layer | Normalise every source to canonical models | `DATA_PROVIDER_LAYER.md` |
| Instrument master | Stable `iid`, symbol history, tick size, lot size | Daily refresh, change log |
| Feed manager | Connections, heartbeat, reconnect, failover, health metrics | One process per provider family |
| Bar builder | Ticks to 1m bars, continuous aggregates for higher timeframes | Timescale continuous aggregates |
| Analytics core | Point-in-time dataset access for scanners and backtests | Polars + DuckDB over Parquet |
| Profile engine | TPO and volume profile (extends the current app) | Value area, IB, day types |
| Orderflow engine | Delta, CVD, imbalance, absorption with quality labels | `ORDERFLOW_ENGINE.md` |
| Structure engine | Swing structure, liquidity, FVG, order blocks (explicit rules) | Shared by scanner and teaching |
| Scanner engine | Logic-graph evaluation over a universe | `SCANNER_ENGINE.md` |
| Backtest engine | Events, costs, walk-forward, Monte Carlo | `BACKTEST_ENGINE.md` |
| Learning engine | Concept graph, lessons, annotations on live charts | `LEARNING_ENGINE.md` |
| AI service | Natural language to validated logic graph | `AI_ARCHITECTURE.md` |
| Realtime gateway | Fan-out of quotes and signals to browsers | Redis pub/sub behind WebSocket |

## 3. Realtime path
`provider socket -> normaliser -> (a) Redis latest + pub/sub, (b) bar builder, (c) tick buffer -> Timescale`.
Browser sockets subscribe to channels by `iid` and timeframe. Backpressure: drop intermediate ticks to the latest
per symbol for UI fan-out (conflation); never conflate on the storage path.

## 4. Batch path
EOD loader (NSE files) and backfills run as queued jobs, write raw responses to Parquet first, then promote to
the validated store after the normalisation gates pass. Every promoted dataset gets a `data_version`.

## 5. Scalability architecture

| Stage | Users | Shape | Triggers to move on |
|---|---|---|---|
| S0 personal | 1 | One VPS, Docker Compose, Postgres + Redis in containers | Need a second user |
| S1 early SaaS | up to ~1k | Managed Postgres/Timescale, Redis, 2 to 3 app replicas, worker pool, object storage | p95 API above target, worker queue lag, feed fan-out CPU |
| S2 growth | up to ~50k | Separate feed service, read replicas, per-tenant scan quotas, Redis cluster | Sustained fan-out above one node's capacity |
| S3 institutional | enterprise | Kafka (or Redpanda) for tick distribution, Kubernetes, tenant isolation, SSO, private deployments | Multiple consumers per stream, replay/audit needs, dedicated clusters |

Why not Kafka and Kubernetes now: the bottleneck in the first stages is **data licensing and honest data**, not
message throughput. A single Redis stream handles tens of thousands of messages per second [U]. Introduce Kafka
when several independent services must consume and replay the same tick stream.

Known scaling hot spots:
1. **Per-user broker connections.** With bring-your-own-keys, each user holds their own broker session and socket
   budget; the platform multiplexes at the application layer, not the exchange layer.
2. **Scan cost.** A 10-year, 2,000-symbol scan is a columnar workload; run in DuckDB/Polars on Parquet with
   partition pruning; cache by `(scan_hash, data_version)`.
3. **Backtest fan-out.** Walk-forward and Monte Carlo are embarrassingly parallel; schedule across workers with
   per-tenant quotas.
4. **Chart rendering.** TPO and footprint must be canvas-rendered with level-of-detail; Lightweight Charts has no
   native footprint or TPO, so custom layers are required.

## 6. Cost architecture (order-of-magnitude estimates, validate with quotes)

| Stage | Monthly infrastructure | Dominant risk |
|---|---|---|
| S0 personal | about USD 10 to 60 (one VPS, domain, backups) | None material |
| S1 early SaaS | about USD 300 to 1,500 (managed DB, Redis, 2 to 3 nodes, storage, monitoring, LLM calls) | **Data licensing** (unknown, could exceed infra), LLM cost |
| S2 growth | about USD 3k to 15k | Egress, tick storage, support |
| S3 institutional | custom | Compliance, SLAs |

Other costs: exchange data licences (request NSE Data's current tariffs; not published in the policy read [V]),
historical vendor if intraday history is required, LLM inference (cap per user, cache aggressively), security
audit before first paying customer.

Cost controls: tick retention windows (for example 7 to 30 days of ticks in Timescale, compress older, archive to
Parquet), per-tenant quotas, cache-by-hash for scans and backtests, spot/preemptible workers for backtests.

## 7. Observability
OpenTelemetry traces and metrics, Prometheus + Grafana, Sentry for errors. Golden signals per component plus
domain metrics: feed latency, staleness, normalisation rejects, scan duration, backtest queue lag, LLM cost per
request. Structured logs; no secrets or full tick payloads in logs.

## 8. Deployment
Docker images (non-root, read-only filesystem, minimal base), GitHub Actions CI/CD with tests, SAST,
dependency and image scanning, signed images. Terraform for environments. Cloudflare in front. Kubernetes only
at S3; until then Compose or a managed container service.

## 9. Evolution of the current app
The existing FastAPI scanner (strategies, rule builder, Market Profile, security middleware, 53 tests) becomes
the seed: its rule JSON becomes the logic-graph AST, its profile engine moves into the profile engine, its
provider interface becomes the first port. Its **BUY/SELL output is retired** (ADR-007).
