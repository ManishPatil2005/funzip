# Product Requirements Document

Working name: **Market Intelligence Platform** (final name TBD)

## 1. Vision
Teach traders how markets operate, and let them create, test and validate ideas using data. Not a signal
service. See RESEARCH.md §3.

## 2. Users and jobs to be done

| Persona | Job | Success looks like |
|---|---|---|
| Learner (Aarav) | "Help me understand why price reacted here" | Completes a learning path, can explain a session's auction |
| Serious retail (Priya) | "Test my idea before I risk money" | Gets a reproducible backtest with out-of-sample results and costs |
| Professional / prop (Rahul) | "Scan the market for my setup and export the evidence" | Historical scan results exported with manifests |
| Educator (Meera) | "Teach with live annotated examples" | Shares frozen annotated sessions with a class |
| Small fund / institution | "Research at scale with an audit trail" | API access, reproducible runs, SSO, private data |

## 3. Scope by capability

| Capability | Summary | Phase |
|---|---|---|
| Provider abstraction + Angel One | Replace yfinance; canonical models; instrument master | 1 |
| Price normalization and verification | No chart renders unverified data | 1 |
| Feed Health Engine and status dashboard | Heartbeat, reconnect, failover, latency | 1 |
| Historical store and EOD pipeline | Verified daily history, adjusted, versioned | 2 |
| Scanner v2 (logic graph, visual builder) | AND/OR/NOT, nesting, templates, versions | 2 |
| Historical scanner replay and export | 1/3/5/10 years, CSV/Parquet/JSON, manifests | 2 |
| Market and Volume Profile v2 | Context outputs instead of BUY/SELL, daily and composite profiles | 3 |
| Learning mode | Concept graph, lessons, "Explain" overlay | 3 onward |
| Backtesting v1 | Single stock, portfolio, costs, out-of-sample | 4 |
| Orderflow (crypto first, then NSE estimated) | Footprint, delta, CVD, imbalance, absorption with quality labels | 5 |
| Heatmaps | Sector, market, RS, volume, participation, breadth, rotation | 6 |
| Structure engine, ICT/SMC concepts | Explicit rule definitions, shared with scanner | 6 to 7 |
| Natural language strategy generator | Text to validated graph to backtest to report | 7 |
| Advanced backtests | Walk-forward, Monte Carlo, robustness, sensitivity, regime, event | 8 |
| Options backtests, news backtests | Data-gated | 8+ |
| SaaS hardening | Multi-tenant, billing, RBAC, audit, SSO, public API | 9 |

## 4. Functional requirements (selected, testable)

**FR-1 Provider switching.** Changing the primary provider for a segment is a configuration change; no business
module imports a provider SDK.
**FR-2 Chart integrity.** A series failing identity, scale or tick-size checks is quarantined and not rendered;
the user sees why.
**FR-3 Feed transparency.** The UI shows per provider and segment the state, last-tick age, latency and next
retry. The text "connect feeder" never appears without cause and recovery information.
**FR-4 Reproducibility.** Any scan or backtest can be re-run from its manifest and match.
**FR-5 Historical scans.** Users select date/range, universe, sector and strategy; results export as CSV, Parquet
and JSON with manifests.
**FR-6 Language policy.** No product surface outputs BUY, SELL or HOLD; outputs are context, scenarios, risk
areas and teaching notes.
**FR-7 Data quality labels.** Orderflow outputs always display `exact`, `estimated` or `bar-approximated`.
**FR-8 Honest backtests.** Reports always show cost assumptions, trial count, in-sample vs out-of-sample.
**FR-9 No execution.** The product places no orders and holds no execution-capable keys.
**FR-10 Auditability.** Security-relevant actions are in a tamper-evident audit log.

## 5. Non-functional requirements
- Availability: 99.5% (S1) for the web app; feed health shown regardless.
- Latency: quote to browser p95 under 500 ms (S1); interactive scan preview p95 under 1 s.
- Accuracy: price parity within one tick on closed bars against the independent anchor.
- Security: OWASP ASVS L2; see SECURITY.md.
- Accessibility: WCAG 2.2 AA for core flows.
- Localisation-ready; IST-aware sessions.

## 6. Non-goals
Order placement, trade signals, portfolio recommendations, copy trading, guaranteed-return claims.

## 7. Success metrics
Learning: lesson completion, quiz gain, journal accuracy. Product: weekly active researchers, scans and
backtests per user, reproducibility rate. Trust: data-incident count, quarantine catches, time-to-detect feed
failures. Business: conversion free to paid, retention at 90 days, B2B pilots.

## 8. Assumptions and open questions
1. Personal/self-hosted first, SaaS later (needs data licensing). **Confirm.**
2. Angel One read-only use is unaffected by the 2026 static-IP rules. **Confirm with Angel.**
3. Forex source is undecided (Delta docs read did not list forex).
4. Intraday history depth beyond what we record needs a paid vendor decision.
5. Do you want to keep Kafka/Kubernetes from day one, or accept the staged plan (ADR-004)?
