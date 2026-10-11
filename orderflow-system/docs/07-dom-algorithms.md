# 07 · DOM / Order-Book Algorithms (code: `orderbook.py`, `heatmap.py`)

**Book state.** `OrderBook` keyed by row; `apply_snapshot` replaces, `apply_update(side, price, qty)` sets (qty 0 deletes). Spread in ticks; `levels(side, n)` best-first.

**Book imbalance.** `(B − A)/(B + A)` over top *n* levels, in [−1, 1]; weights flat or `1/(i+1)` (near-touch counts more). Resting size is intent, not execution, and can vanish.

**Walls.** A level is a wall if `qty ≥ k × median(qty of inspected levels)` (k = 3, optional floor). Median (not mean) so one wall cannot inflate its own threshold.

**Wall lifecycle (`WallTracker`).** Tracks wall state per (side,row): first seen, peak qty, executed volume at the price (from trades). When quantity falls below `vanish_fraction` (20%) of peak the wall is removed with outcome **consumed** (executed share ≥ 50%) or **pulled** (otherwise), plus lifetime and whether price approached within 3 ticks.

**Spoof-like pattern.** ≥ 3 *pulled*, *approached*, short-lived (≤ 10 s), ~untraded (≤ 10% executed) wall events on one side within 60 s. Reported as a pattern with alternatives (market-maker repricing is routine) and the limitation that intent is unobservable. Confidence capped at ESTIMATED tier.

**Iceberg-like.** A level whose cumulative executions exceed 3× the largest displayed size, with ≥ 3 refills. Hidden size is never observed — inference from refill behaviour. Needs aligned trades+depth.

**Heatmap.** Each snapshot is a step function until the next. Matrix rows×time columns; mode `max` (shows brief walls) or `avg` (time-weighted, shows persistence). **Intensity** → [0,1]: linear, log (`log1p(min(q,cap))/log1p(cap)`), or percentile rank; `cap` = 99th percentile of non-zero cells so one huge wall does not flatten the map. Colour ramp dark blue → teal → yellow → red (red = most liquidity, the Bookmap convention [S5]); front end mirrors the stops (test-pinned).

**Feed caveat.** NSE/MCX via Angel: 5 levels, ~1 s → coarse heatmap, spoof/iceberg logic unreliable (event-level data absent). Crypto via Delta: 20 levels; update channel gives better timing.
