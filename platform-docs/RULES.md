# Rules

Binding rules for every contributor (human or AI). Violations block merge.

## 1. Product and language rules
1. **No BUY / SELL / HOLD** anywhere in UI, API responses, exports, lesson text or AI output. Use context,
   scenarios, risk areas and teaching notes.
2. No price targets or entries presented as instructions; levels are labelled "potential support/resistance
   region" or "reference level" with the reasoning.
3. No "will", "guaranteed", "sure". Use conditional, attributive language ("according to Auction Market Theory").
4. Every orderflow observation shows `data_quality` and `method`.
5. Every statistic shows its sample size and period.
6. No order placement and no storage of execution-capable credentials.
7. Disclaimers appear wherever outputs could be read as advice; they supplement the language rules, not replace them.

## 2. Data rules
1. Business code depends on provider **ports only**; no broker SDK imports outside adapters.
2. Timestamps are UTC internally, IST for display; sessions come from the trading calendar.
3. Prices are `Decimal` or integer ticks in storage and calculation boundaries; tick-size validated.
4. **Nothing is charted or scanned until it passes the normalisation gates** (identity, scale, tick size,
   outliers, adjustment consistency). Failures are quarantined, never silently dropped or "fixed".
5. Adjusted and raw series are never mixed; the flag is always stored.
6. Every dataset has a `data_version`; every scan and backtest records it.
7. Point-in-time always: no lookahead, no survivorship bias, fundamentals by report date.
8. Provider rate limits are enforced by the governor; no direct HTTP calls to providers outside adapters.

## 3. Engineering rules
1. Modular monolith boundaries: modules interact through their public interfaces only (import-linter enforced).
2. Type hints everywhere (mypy strict on core modules), TypeScript strict mode.
3. Pure functions for calculations; I/O at the edges; one implementation shared by streaming and batch paths.
4. Idempotent loaders and consumers; retries with backoff and jitter; timeouts on every external call.
5. No dynamic evaluation of user input; no string-built SQL.
6. Config via environment; no secrets in code, logs, tests or images; secret scanning in CI.
7. Structured logging with correlation IDs; no tick payload or secret in logs.
8. Database changes through migrations only, reversible where possible, reviewed for lock impact.
9. Feature flags for risky changes; every provider cutover has a rollback.
10. Tests: new behaviour needs tests; bug fixes need a regression test; critical modules above 90% coverage.

## 4. Process rules
1. Work in phases: **Research, Architecture, Security Review, Implementation Plan, Testing Plan, Code**. Do not
   skip ahead.
2. End of phase: report Risks, Limitations, Scaling Challenges, Technical Debt, Cost Estimate, Recommended Next
   Step.
3. Decisions are recorded in DECISIONS.md (ADR format). Deviations from the brief are flagged to the owner.
4. Definition of done: code, tests, docs, security checklist, observability, migration notes, language-policy
   check, reviewer sign-off.
5. Evidence tags: claims about external systems carry a source and date; unverified claims are marked.
6. Dependencies: pinned, audited, minimal; new dependency needs a one-line justification.
7. Secrets from the owner are never requested in chat; use the secure intake in SECURITY.md.

## 5. AI-assistant rules
1. Read MEMORY.md at the start of a session; update it at the end.
2. Do not invent API behaviour; verify against documentation or mark as unverified.
3. Do not weaken security or language rules to make a feature easier.
4. Prefer small, reviewable changes with tests.
