# Roadmap

Estimates assume 1 to 2 engineers and are ranges, not commitments. Each phase follows the cycle: Research,
Architecture, Security Review, Implementation Plan, Testing Plan, Code, then the phase report.

| Phase | Theme | Main deliverables | Exit criteria | Est. |
|---|---|---|---|---|
| 0 | Research and blueprint | These documents | Owner approves ADRs | done |
| 1 | Foundation and data truth | Ports, canonical models, instrument master, Angel adapter (stocks), normalisation gates (Issue 1), Feed Health Engine and status page (Issue 2), shadow mode vs yfinance | Golden-set price parity; chaos tests pass; one clean month in shadow mode | 5 to 8 weeks |
| 2 | History and scanner v2 | NSE EOD pipeline, adjustment engine, dataset versions, logic-graph scanner, visual builder, replay and CSV/Parquet/JSON export (Issue 3) | Reproducible exports; 10-year daily replay under target | 6 to 8 weeks |
| 3 | Profile v2 and learning | Context outputs replacing BUY/SELL, composite profiles, volume profile, learning engine skeleton, language linter, first 10 lessons | No banned terms anywhere; lessons reviewed | 5 to 7 weeks |
| 4 | Backtesting v1 | Event-driven engine, costs, single and portfolio, in/out-of-sample, trial ledger, reports (Issue 4 part 1) | Known-answer and no-lookahead tests pass | 6 to 8 weeks |
| 5 | Orderflow | Delta Exchange adapter (after stocks), footprint, CVD, imbalance, absorption with quality labels; NSE estimated mode | Crypto exact flow validated; estimated labels everywhere | 6 to 8 weeks |
| 6 | Heatmaps and structure | Sector/market/breadth/RS/volume/participation heatmaps; structure engine (swings, liquidity, FVG, order blocks) | Definitions documented; parity tests | 5 to 7 weeks |
| 7 | AI strategy generator | NL to graph, explain-back, auto backtest and report, evaluation suite | Golden set pass rate target met; adversarial set clean | 4 to 6 weeks |
| 8 | Advanced backtesting | Walk-forward, Monte Carlo, robustness, sensitivity, regime and event tests; options once chains exist | Reproducibility; compute quotas | 6 to 8 weeks |
| 9 | SaaS hardening | Multi-tenancy, RBAC, billing, audit, per-user broker keys, data licensing decision, penetration test, public API | Pen test findings closed; legal review done | 8 to 12 weeks |
| 10 | Institutional | SSO, private deployments, Kafka/Kubernetes if triggered, SLAs, premium data adapters | Contracted pilots | ongoing |

Dependencies: Phase 1 gates everything. Legal and data-licensing work (Phase 9 items) should **start in
parallel** from Phase 2 because they have long lead times.

## Next three milestones after approval
1. Obtain the current repository; reproduce Issues 1 and 2 and confirm root causes.
2. Implement ports and the instrument master with `YFinanceProvider` and `SyntheticProvider` behind them.
3. Implement the normalisation gates and golden-set tests; then the Angel adapter.
