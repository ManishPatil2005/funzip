# Backtest Engine

Purpose: let users **validate ideas honestly**. The engine is built to resist flattering results.

## 1. Modes (Issue 4)

| Mode | What it does | Key requirement |
|---|---|---|
| Single stock | One instrument, one graph | Clean adjusted prices |
| Portfolio | Many instruments, capital and position limits, correlation | Position sizing, capital model |
| Sector | Aggregate by sector, relative performance | Point-in-time sector map |
| Market regime | Split results by labelled regimes (trend, balance, high/low volatility) | Open, rule-based regime definitions |
| Event | Performance around earnings, expiries, index changes, macro dates | Event calendar with timestamps |
| News | Performance around tagged headlines | **Licensed point-in-time news archive** (not available today) |
| Options strategy | Multi-leg payoffs, Greeks, expiry handling | Historical chains with strike-wise prices and OI (must be recorded forward [V]) |
| Walk-forward | Rolling in-sample optimisation then out-of-sample test | Parameter grids, window rules |
| Monte Carlo | Resample trades or returns to estimate outcome dispersion | Seeded randomness, block bootstrap |
| Robustness | Perturb parameters, costs, entry timing, data | Batch runs |
| Sensitivity | Heatmaps of metric vs parameters | Batch runs |

News and options backtests are **data-gated**: the UI shows "unavailable until data is licensed/recorded" rather
than producing weak results.

## 2. Execution model
- **Event-driven core** for portfolio realism; **vectorised fast path** for single-signal screens. Both must
  produce identical results on shared test cases.
- Signals are computed at bar close; orders fill at the **next bar open** by default (no same-bar fills at the
  signal price). Alternative fill models are explicit options.
- **No lookahead:** the data accessor exposes only history up to the decision time; property-based tests assert
  that truncating future data never changes past decisions.
- Corporate actions: adjustments applied by us from the verified factor table; trades record raw and adjusted
  prices.
- Intrabar ambiguity (stop and target both inside one bar): resolved pessimistically by default, configurable.
- Position sizing models: fixed quantity, fixed risk (ATR-based), percent equity; capital and margin limits
  enforced; lot sizes and tick sizes respected.

## 3. Costs and slippage
Costs are a **configurable schedule**, not hard-coded numbers: brokerage, STT/CTT, exchange transaction charges,
GST, stamp duty, SEBI fees and DP charges for delivery, by segment. Rates change, so the schedule is versioned
data with an effective date and a source note. Slippage models: fixed ticks, percent of ATR, volume-participation
(limit trade size to a fraction of bar volume), spread-based when quotes exist. The report states the model used.

## 4. Metrics
Return, CAGR, volatility, Sharpe and Sortino, max drawdown and duration, Calmar, hit rate, average win/loss,
expectancy, profit factor, exposure, turnover, trade count, MAE/MFE distributions, rolling performance,
benchmark-relative statistics, **cost drag**, regime breakdown.

## 5. Guarding against self-deception
- **Trial ledger:** counts every variant a user tried for a strategy; reports use it to compute a **deflated
  Sharpe** or multiple-testing-adjusted significance.
- **Mandatory out-of-sample:** reports split in-sample and out-of-sample; results from tuning on the full period
  are labelled "in-sample only".
- **Minimum sample warnings:** few trades, concentrated returns, regime dependence.
- **Walk-forward** with anchored and rolling windows; purge/embargo around splits to avoid leakage.
- **Monte Carlo:** shuffle/bootstrap trade sequences and block-bootstrap returns to show drawdown and ending
  equity distributions; fixed seeds recorded for reproduction.
- **Robustness:** parameters +/- steps, costs x2, entry delayed by one bar, random data dropout; a strategy that
  collapses under small changes is flagged fragile.
- **Survivorship:** point-in-time universes; delisted names included.

## 6. Reproducibility
`backtest = f(graph_hash, config, universe_ref, data_version, seed)`. Everything is stored; one click re-runs
and must match. Reports embed the manifest.

## 7. Report structure
1. Summary and the exact definition of the idea (explained back from the graph).
2. Data: range, instruments, `data_version`, quality notes.
3. Assumptions: costs, slippage, fills, sizing.
4. Results: in-sample vs out-of-sample, equity curve, drawdowns, distribution of trades.
5. Robustness: sensitivity heatmaps, Monte Carlo bands, regime split.
6. Honest limitations: trial count, sample size, what the test cannot show.
7. Teaching notes linking to relevant lessons.
No forecasts and no recommendations.

## 8. Compute plan
Jobs on a worker pool; parallel across symbols and parameter sets; results streamed to the UI; spot/preemptible
capacity; quotas per tenant and plan.

## 9. Risks
Cost-model drift (versioned schedules), data gaps, over-optimistic fills (pessimistic defaults), slow large
sweeps (quotas, sampling previews).
