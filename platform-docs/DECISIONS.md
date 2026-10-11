# Decisions (ADR log)

Format: context, decision, consequences, status. **Proposed** means it needs the owner's approval.

## ADR-001 Modular monolith first
Context: small team, fast iteration, strong need for consistency. Decision: one deployable with enforced module
boundaries mirroring future services. Consequences: simple ops now; split along the same seams later.
Status: Proposed.

## ADR-002 Bring-your-own broker keys for multi-user mode
Context: exchange data redistribution is licensed [V NSE policy]; one shared broker login for many users is a
licensing and security risk. Decision: each user connects their own provider credentials; platform multiplexes at
the application layer. Consequences: no shared data bill early; onboarding friction; credential security
becomes central. Status: Proposed. Revisit if the company signs a data vendor licence.

## ADR-003 PostgreSQL + TimescaleDB + Parquet/DuckDB
Decision: Timescale for hot/warm series and metadata; Parquet with DuckDB/Polars for cold analytics and exports.
Consequences: one relational system for transactions, columnar files for heavy scans. Status: Proposed
(matches your stack).

## ADR-004 Defer Kafka and Kubernetes
Context: the brief lists both. Early bottlenecks are data licensing and correctness, not message throughput;
Kafka and Kubernetes add operational load and failure modes. Decision: Redis streams/pub/sub and Compose or a
managed container service until triggers in ARCHITECTURE §5 occur, then adopt Kafka (or Redpanda) and
Kubernetes. Consequences: faster delivery; some re-plumbing later, limited by the ports design.
Status: **Proposed, deviates from the brief; needs your decision.**

## ADR-005 Provider ports and capability descriptors
Decision: seven ports plus declared capabilities; contract test suite per provider. Consequences: new providers
need no architecture change. Status: Proposed.

## ADR-006 Strategies are data (logic graph AST), never code
Decision: scanners and strategies are validated JSON graphs interpreted by a fixed engine; AI emits the same
graph. Consequences: safe by construction, reproducible, diffable; custom Python indicators are a later,
sandboxed feature. Status: Proposed (continues the current app's design).

## ADR-007 Retire BUY/SELL output
Context: the delivered v1 scanner and Market Profile bias output BUY/SELL/NEUTRAL; the new brief forbids it.
Decision: replace with context, scenarios, risk areas and teaching notes; keep the scoring machinery internally
as "evidence weights" for explanation only, hidden from users unless expressed as observations.
Consequences: aligns with education positioning and reduces advice-related risk (not eliminates). Status: Proposed.

## ADR-008 Daily history from NSE end-of-day files, verified against broker candles
Context: Angel candle API caps at 500 records per call and is rate limited [V/A]. Decision: NSE EOD files are the
daily backbone; adjust for corporate actions ourselves; cross-check against broker data. Consequences: cheap,
deep daily history; terms of use must be re-checked. Status: Proposed.

## ADR-009 Intraday history policy
Decision: record intraday and option-chain data forward from go-live; do not promise multi-year intraday until a
licensed vendor is chosen. Consequences: honest UI about depth; some features (long intraday replay, options
backtests) grow over time. Status: Proposed.

## ADR-010 Charts: Lightweight Charts plus custom canvas layers
Decision: use Lightweight Charts for standard series; build TPO, footprint, profile and heatmaps as custom
canvas/WebGL layers. Consequences: more front-end work, full control and performance. Status: Proposed.

## ADR-011 Orderflow honesty tiers
Decision: `exact`, `estimated`, `bar_approximated` quality tiers surfaced everywhere; concepts gated by tier.
Consequences: less flashy than competitors on NSE, more trustworthy. Status: Proposed.

## ADR-012 Natural language to constrained graph with explain-back
Decision: LLM output validated against schema; user confirms definitions; numbers in reports inserted by code.
Status: Proposed.

## ADR-013 Keep Python/FastAPI core; add Next.js front end
Decision: evolve the existing FastAPI app; new Next.js UI consumes its API; migrate screens incrementally.
Consequences: reuse of 53 tests and security middleware. Status: Proposed.

## ADR-014 No credential values in chat
Decision: secrets are supplied through a local env file or secrets manager that the owner creates; the assistant
receives variable names only. Status: **Adopted** (see SECURITY.md §3).
