# Phase 0 Report

Phase: Research and architecture blueprint. Date: 2026-10-10. Code written: none (per the brief).

## What was produced
Research study, product requirements, architecture, security architecture, data-provider layer, database schema,
orderflow, scanner, backtest and learning engine specifications, AI architecture, test plan, rules, decisions,
roadmap, startup strategy, project memory. See MEMORY.md for the map.

## Findings that change the plan
1. **True NSE order flow is not available to retail APIs.** Delta and footprint on NSE/MCX will be *estimated* and
   labelled so. Crypto can be exact. This shapes the roadmap (crypto first for orderflow).
2. **Angel One is a poor source for deep history.** 500 records per candle call and strict rate limits make years
   of intraday history impractical. Daily history should come from NSE end-of-day files; intraday must be recorded
   forward or bought.
3. **Credentials list is incomplete.** Angel login also needs the account **PIN**. And please never paste
   credential values into chat; use a local env file or a secrets manager.
4. **Licensing decides the business model.** Redistributing NSE-derived data to other users needs agreements; a
   bring-your-own-keys design avoids a shared data bill early. Needs legal advice.
5. **The brief's stack is partly premature.** Kafka and Kubernetes are deferred, not dropped (ADR-004).
6. **The v1 scanner conflicts with the new brief.** It outputs BUY/SELL; ADR-007 retires that.
7. **Delta docs read did not list forex.** A separate forex source decision is needed.

## Risks
| Risk | Severity | Mitigation |
|---|---|---|
| Regulatory treatment as advice or research | High | Language policy, no execution, legal opinion |
| Data licensing cost or refusal | High | BYO keys, phased scope, early vendor talks |
| Over-claiming order flow on NSE | High | Quality tiers and labels |
| Credential theft | High | Vault/KMS, avoid storing TOTP in SaaS mode, audit |
| Scope breadth (many engines) | High | Strict phasing and exit criteria |
| Provider API changes or outages | Medium | Ports, failover, contract tests |
| Overfit backtests mislead users | Medium | Trial ledger, out-of-sample, fragility flags |

## Limitations of this study
Several competitor details (Chartink, Screener, ODX, Sensibull) were not verified this session [U]. Angel rate
limits come from a 2024 forum table and the candle cap from an admin comment; depth-20 and token limits came
from forum posts; several Angel pages were access-restricted. Delta's historical-candles section was truncated.
Regulatory statements are summaries, not legal advice. Costs are order-of-magnitude.

## Scaling challenges
Per-user broker sockets, tick storage growth, large replays, backtest fan-out, canvas performance for TPO and
footprint, multi-tenant isolation.

## Technical debt carried in
v1 app: yfinance dependency and MCX proxies, BUY/SELL output, SQLite, per-process rate limiter and cache, no
instrument master, no data versioning. All have planned replacements.

## Cost estimate
Phase 1 to 3 engineering: roughly 16 to 23 engineer-weeks. Infrastructure for personal use: about USD 10 to 60 per
month. Data licensing: unknown until quotes. Legal opinion: budget needed.

## Recommended next step
1. Review and approve or amend the Proposed ADRs, especially ADR-004 and ADR-007.
2. Share the current repository so Issues 1 to 4 are diagnosed from real code.
3. Confirm with Angel One support that read-only market data is unaffected by the 2026 static-IP rules, and
   confirm historical limits and depth entitlements for your account.
4. Then begin Phase 1: ports, instrument master and the normalisation gates (Issue 1) before any Angel
   connection, so wrong data can never reach a chart again.

Credentials: not requested yet. They will be requested only when Phase 1 reaches the Angel integration, as
variable names to set in your own environment, never as values in chat.
