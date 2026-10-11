# Test Plan

## 1. Strategy
Test pyramid with domain-specific gates. Every phase ends with a **phase gate**: all gates below that apply must
pass before the next phase starts.

| Layer | Examples | Tooling |
|---|---|---|
| Unit | Indicators, profile calculations, parsers, classification rules, linters | pytest, vitest |
| Property-based | No-lookahead, idempotent merges, price-scale invariants, graph validation | Hypothesis |
| Contract | Every provider passes the shared provider contract suite | pytest + recorded fixtures |
| Integration | API + DB + Redis, normalisation pipeline end to end | Testcontainers |
| Data quality | Cross-source parity, tick-size validity, gap and outlier detection | Great Expectations style checks |
| Golden / regression | Known-answer backtests, profile outputs for frozen sessions | Snapshot tests |
| Chaos | Kill sockets, delay quotes, expire tokens, corrupt a bar | Fault injection harness |
| Performance | Scan, backtest, fan-out throughput | k6, Locust, pytest-benchmark |
| Security | SAST, dependency, container, DAST, authz tests | bandit, pip-audit, npm audit, Trivy, OWASP ZAP |
| UX / accessibility | Core flows, keyboard, contrast, screen reader | Playwright, axe |
| AI evaluation | NL to AST golden set, adversarial prompts, language linter | Eval harness in CI |

## 2. Critical issues: acceptance tests

**Issue 1: price scaling.** Golden set of at least 50 instruments including prices above Rs 10,000, recent splits
and bonuses, indices and low-priced stocks. For each: charted latest price within 0.5% of the independent anchor;
visible range contains the validated bars; injecting a x100, x0.01 or x10 scaled series is **quarantined and not
drawn**; a wrong ISIN/name mapping blocks the series; outlier bars are flagged, not dropped.

**Issue 2: feed health.** Simulated socket drop during session: reconnect within the backoff schedule, resubscribe
from desired state, gaps backfilled, no duplicate bars. Token expiry: automatic re-login. Primary provider hard
down: failover within the threshold, labelled data, clean fail-back without flapping. Outside session: state is
`CLOSED`, never `STALE`. UI always shows a reason and timer.

**Issue 3: scanner export.** For 1, 3, 5 and 10-year ranges: row counts match an independent computation on a
sample; CSV, Parquet and JSON contain identical rows; manifest hashes verify; re-run with the same
`(graph, universe, as_of, data_version)` is byte-identical; selectors (date, universe, sector, strategy) filter
correctly; unavailable depth is reported, not silently truncated.

**Issue 4: backtesting.** Known-answer cases (hand-computed trades and costs); vectorised vs event-driven parity;
lookahead property tests; walk-forward windows never overlap illegally; Monte Carlo reproducible by seed;
robustness and sensitivity jobs complete and are cached; cost schedule changes alter results as expected.

## 3. Domain tests
- Market Profile: frozen sessions with hand-verified POC, value area, IB, day type and open type.
- Orderflow: classification methods against labelled synthetic ticks; parity between streaming and batch.
- Language policy: no generated or authored text contains banned trade-instruction terms.
- Education: every concept has a lesson, a definition and a limitation note.

## 4. Security tests (per phase gate)
Authorisation matrix (every role against every endpoint); tenancy isolation (cross-tenant access attempts);
injection and SSRF probes; secrets never in logs or responses (log scanning); credential service access audited;
rate limits enforced; dependency and image scans clean of high severity; threat-model review updated.
Pre-launch: independent penetration test.

## 5. Environments and data
Local (synthetic provider), CI (recorded fixtures), staging (real provider read-only, licensed data only),
production. Test data never contains real user credentials.

## 6. Entry and exit criteria
Entry: phase design reviewed, acceptance tests written. Exit: all tests pass, coverage targets met (critical
modules above 90% line coverage, others above 75%), no open high-severity defects, security review signed,
documentation and DECISIONS updated, phase report (risks, limitations, scaling, debt, cost, next step) written.

## 7. Existing assets
The current app has 53 passing tests covering indicators, rule builder safety, profile logic, API validation,
authentication and rate limiting; they migrate into the new suite and expand.
