# 08 · Strategy Framework (code: `ofx/orderflow/detectors.py`)

**Output contract.** Every detector returns `Observation(kind, window, price range, summary, evidence, data_quality, method, confidence, alternative_readings, limitations, teaching_ref)`. Summary text is passed through a language linter at construction; instructions to act cannot be produced. Confidence ≤ 1.0 / 0.6 / 0.35 for EXACT / ESTIMATED / BAR_APPROXIMATED. Thresholds below are **starting parameters [I]**, not validated edges; they must be tested per instrument before being trusted.

| # | Detector | Math / rule | Inputs | Outputs | Edge cases | False-signal conditions |
|---|---|---|---|---|---|---|
| 1 | Delta divergence | Confirmed pivots (left 2, right 2) on bar highs/lows. For consecutive same-kind pivots i<j with price_j beyond price_i: `z = (CVD_j − CVD_i)/(σ_Δ·√k)`, k=j−i. Report if z ≤ −z_min (highs) / ≥ z_min (lows). Confidence = min(1,\|z\|/(2·z_min)) capped | footprint bars with CVD | `delta_divergence_high/low` | skip pairs across CVD reset, gap > 40 bars, unknown share > 30%; σ=0 → none | Few pivots; side-estimation error; strong trends where delta lags |
| 2 | Absorption | Bar volume ≥ 80th pct of prior 20 bars; \|body\|/range ≤ 0.6; \|Δ\|/V ≥ 0.2; progress in delta direction ≤ 0.35·range | bars | `absorption_ask_flow/bid_flow` | zero-range skipped; warm-up needs 20 bars | Pauses before continuation; news bars |
| 3 | Exhaustion | New extreme vs prior 10 bars with ≥ 2 of: finished print (zero ask at top row / zero bid at bottom row), thin extreme (top-2 rows ≤ 10% of volume), delta fade (≤ 50% of previous bar's delta, same sign as move) | bars | `exhaustion_top/bottom` | needs previous bar | Thin sessions, fast markets; momentum may continue |
| 4 | Liquidity sweep | Pivot levels (left/right 3), built causally; equal levels within 2 ticks count as touches. Breach ≥ 1 tick beyond; close back inside within 3 bars → **sweep**; else **acceptance beyond level**. Evidence: excursion ticks, volume and delta beyond the level | bars, tick | `liquidity_sweep_*`, `acceptance_beyond_*` | breaches too near data end are not reported; one event per level/bar | Level is a prior pivot, not a known order cluster; "stop run" is inference |
| 5 | Imbalance cluster | Stacked imbalances (≥ 3 rows) merged across bars (same side, row overlap, ≤ 10 bars apart); status untested / retested / traded through | bars | `imbalance_cluster_ask/bid` | merges widen the zone | Ratio and min volume tunable; retest alone says nothing about direction |
| 6 | CVD trend | Last 20 bars of one session: Theil–Sen slope (median pairwise slope; robust to one huge bar) normalised by mean bar volume; Kendall τ for CVD and price, significance \|τ\| ≥ 0.3. Classes: aligned, diverging, flow_without_progress, price_without_flow, balanced | bars | `cvd_trend_<class>` | < window bars or a session reset inside → none | Short windows; level depends on reset point (only slope used) |

Supporting: `large_trades` (prints ≥ 99th percentile qty); wall/spoof/iceberg observations (doc 07).

**Example wording produced:** "Price made a higher high (… ) while cumulative delta made a lower high (z=−1.4): the push higher had less net buyer-initiated volume behind it." Alternatives listed beside it: passive absorption, classification error, delayed continuation.

**Why pivots-confirmed-only:** a pivot that can appear and later vanish is a repainting signal; we accept lag of `right` bars to keep history truthful (backtest = live).

## Scenario rules (strategies as data) — `ofx/strategy.py`
A rule is JSON: `{name, description, window_bars (1-100), all_of: [conditions], none_of: [conditions], teaching_note}`; a condition is `{kind (exact or pattern like "liquidity_sweep_*"), min_confidence, quality_at_least}`. Evaluation anchors on each observation matching the first `all_of` condition; every other condition needs a matching observation within ±`window_bars` bars of the anchor and no `none_of` condition may match there. Overlapping matches report only the first. Result quality = weakest of the evidence; confidence = minimum of the evidence, capped by that quality.
**Why data, not code:** rules are validated (unknown fields, ranges and wording rejected; the language linter runs on name, description and teaching note), evaluated without eval/exec, and safe to accept from users. A match is a *context* ("these observations coincided") with a limitation line; it never states what happens next.
Endpoints: `POST /api/v1/scenarios?iid&tick&start&end&tf` with the rule as body; `GET /api/v1/scenarios/examples`.
