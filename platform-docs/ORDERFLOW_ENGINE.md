# Orderflow Engine

## 1. The honesty rule
Every orderflow output carries `data_quality` (`exact`, `estimated`, `bar_approximated`) and `method`. The UI
shows it next to the chart. If quality is below what a concept needs, the concept is **disabled or labelled
"illustrative"**, not silently approximated.

| Concept | Needs | Crypto (Delta) | NSE/MCX (Angel) | Bars only |
|---|---|---|---|---|
| Bid/ask delta, CVD | Trades with aggressor side | exact | estimated | bar-approximated |
| Footprint | Trades per price level with side | exact | estimated | not available |
| Stacked imbalance | Footprint | exact | estimated, low confidence | no |
| Absorption / exhaustion | Footprint + depth | exact | estimated | no |
| Passive buyers/sellers | L2 depth over time | exact | limited (5 levels, depth-20 beta) | no |
| Liquidity pools / sweeps | Price structure (+ depth for confirmation) | yes | yes (structure-based) | yes (structure-based) |
| Iceberg detection | L3 or executed-vs-displayed at a level | framework only | not feasible | no |
| Spoofing detection | Order-level add/cancel events | research only | not feasible | no |

Basis: Delta exposes L2, trades and candle channels [V]; Indian retail data lacks aggressor tagging and deep
depth [A]; Angel offers LTP/Quote/Snap and a beta 20-level depth mode [V].

## 2. Aggressor classification (when the exchange does not give it)

| Method | Rule | Weakness |
|---|---|---|
| Quote rule | Trade at or above ask is a buy; at or below bid is a sell | Needs synchronised quotes; midpoint trades ambiguous |
| Tick rule | Up-tick buy, down-tick sell, zero-tick inherits the last direction | Noisy in fast markets |
| Lee-Ready | Quote rule, tick rule for midpoint trades | Quote/trade timing mismatch |
| Bar split | Volume split by close position in the bar range | Crude; only for bar-approximated quality |

The engine records the method on every tick and reports an **agreement score** where two methods can be
compared on the same data. Low agreement lowers the displayed confidence.

## 3. Metrics (definitions)
- **Delta** = buy volume minus sell volume in the interval.
- **CVD** = running sum of delta over a session or anchor; session-anchored by default, anchor selectable.
- **Imbalance ratio** at a price = ask-volume at that price divided by bid-volume one level below
  (diagonal, the standard footprint convention); flagged above a configurable ratio (default 3x, minimum volume
  floor to avoid tiny-sample noise).
- **Stacked imbalance** = N consecutive price levels flagged in the same direction (default N=3).
- **Absorption (heuristic):** large aggressive volume into a level with little price progress and the aggressor
  side's delta not translating into movement; requires volume above a rolling percentile and range below a
  rolling percentile.
- **Exhaustion (heuristic):** diminishing aggressive volume at successive extremes with a delta divergence.
- **Delta divergence:** price makes a new extreme while CVD fails to confirm, over a defined swing window.
- **Trapped traders (heuristic):** aggressive volume at an extreme followed by acceptance back through the
  level and adverse movement beyond a threshold.
- **Liquidity sweep:** price trades through a prior swing high/low (or equal highs/lows) and closes back inside
  within K bars; "pool" = clustered equal highs/lows or prior-session extremes.
- **Auction rotation analysis:** rotations between prior value-area edges and POC, counting acceptance versus
  rejection by time spent and volume.
- **Volume shock:** volume above a rolling z-score or percentile threshold relative to same time-of-day.
- **Big bar:** range and volume both above rolling percentiles, with close location within the bar.

All thresholds are named constants with defaults, stored per profile, and shown in the teaching note. They are
**heuristics**, not exchange facts.

## 4. Outputs (never trade instructions)

```
OrderflowObservation {
  iid, ts_range, timeframe,
  observation:  "Aggressive buying volume absorbed between 1,234.0 and 1,235.0 with limited price progress",
  evidence:     { delta, volume_percentile, range_percentile, levels },
  data_quality: "estimated", method: "lee_ready", confidence: 0.55,
  alternative_readings: ["Passive sellers defending a level", "Fresh supply arriving"],
  teaching_note_ref: "absorption",
  limitations: "Delta estimated from quote and trade snapshots; aggressor side not exchange-tagged."
}
```

## 5. Computation design
- Streaming path: per-symbol state machines (current bar footprint, rolling percentiles) updated per tick.
- Batch path: Polars over Parquet ticks for scans and backtests; identical definitions via shared Rust-like pure
  functions in one module so live and historical results agree (tested for parity).
- Storage: footprint cells aggregated per bar `(iid, bar, price_level, bid_vol, ask_vol, trades)`; raw ticks
  retained for a short window only.

## 6. Roadmap within this engine
1. Crypto first (Delta): exact data, validates the engine and the UI.
2. NSE/MCX estimated order flow with prominent quality badges.
3. Depth-based passive liquidity views if depth-20 graduates from beta.
4. Iceberg and spoofing frameworks remain research until a data source supports them (for example paid futures
   feeds via Rithmic or CQG for global instruments).

## 7. Risks
Over-interpreting estimated delta; thresholds tuned to a sample; latency distortions in classification. Mitigation:
quality labels, parity tests, out-of-sample checks, and teaching notes that state limits.
