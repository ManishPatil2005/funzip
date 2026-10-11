# Scanner Engine

## 1. Logic graph (the one representation)
A scanner is an immutable **logic graph** (JSON AST). The visual builder, the natural-language generator, saved
templates and the backtester all read and write the same object. The current app's rule JSON (all/any groups,
operands, 24 indicators) is the starting grammar.

Node types:
- **Operands:** price field, indicator (with params), constant, **concept output** (profile, structure, orderflow),
  fundamental field, options field, event field, time field, cross-sectional rank/percentile.
- **Operators:** `> < >= <= == between`, `crosses_above/below`, `within N bars`, `consecutive N`, `lookback agg`
  (max, min, mean, percentile, count).
- **Logic:** `AND`, `OR`, `NOT`, nested to a bounded depth (default 6) and size (default 60 nodes).
- **Context nodes:** universe filter, sector filter, market-breadth condition, time-of-day window, event window.

Validation (static, deterministic): type and unit checks, lookback sufficiency, **no lookahead**, allowed
nodes only, size limits, deprecation warnings.

## 2. Evaluation model
- Vectorised in Polars over columnar data; multi-symbol evaluation by partitioned lazy frames.
- **Point-in-time semantics:** a condition at time `t` may use only data available at `t` (bar close). Fundamentals
  use reported-date, not period-end date. Universes use historical membership (`index_membership`), avoiding
  survivorship bias.
- Deterministic: result depends only on `(graph_hash, universe_ref, as_of, data_version)`.
- Cache key = that tuple; identical re-runs return instantly and prove reproducibility.

## 3. Historical scanner validation and export (Issue 3)

**Replay mode.** Run the scanner as-of any past date or over a date range: "which symbols matched on each day"
across 1, 3, 5 or 10 years.

Selectors: date or range, universe (index, watchlist, custom, all), sector/industry, strategy and version.
Outputs, per match: symbol, date, the matched conditions with values, price context, and (optionally) forward
statistics such as the next 1/5/20-bar return distribution **computed after the fact and labelled as
hindsight**, for study, not as a forecast.

Exports: **CSV, Parquet, JSON**, each with a `manifest.json`:

```
{ scanner_id, version, graph_hash, universe_ref, date_range, data_version, generated_at,
  row_count, columns: [...], schema_version, quality_summary, notes }
```

Large exports are asynchronous jobs with a signed, expiring download link and a per-tenant quota.

Data constraints (from the research): 10-year **daily** history is feasible from EOD sources; **10-year intraday**
is not available from Angel [V/A]; intraday replay depth is whatever the platform has recorded or licensed.
The UI states the available depth per timeframe before the user runs a long replay.

## 4. Visual no-code builder
- Canvas of condition cards grouped by AND/OR/NOT; drag to nest; inline parameter editors with sensible ranges.
- Live "match count" preview on a sample universe; inspect any symbol to see why it matched or not (per-node
  truth values and the values behind them).
- Templates: save, version (immutable versions, diff view), share by link or workspace, fork.
- Version history with notes; rollback creates a new version, never edits history.

## 5. Filters by family
Indicators; orderflow conditions (quality-gated); volume (relative volume, volume shock, profile levels);
fundamentals (point-in-time); options (OI change, IV percentile, PCR, max pain as defined); events (earnings,
expiry, index changes); time (session segments, day of week, expiry proximity); historical (percentile of own
history, gap statistics).

## 6. Output format (Issue: never BUY/SELL)
A scan result is **"matched conditions" plus context**, not a call:
`Context: price accepted above the prior value area high; volume 2.3x its 20-day same-time average; sector
breadth 68% above 50-day average. Observation only; see teaching note "Acceptance vs rejection".`

## 7. Heatmap engine (shares scanner data)
Heatmaps are pre-aggregated views over the same point-in-time dataset: sector, industry and market heatmaps;
relative-strength; volume; participation (relative volume by time-of-day); breadth (advance/decline, percent
above moving averages); liquidity (spread and depth where available); **institutional rotation** (relative
sector strength change over rolling windows, defined openly and labelled as an indicator of relative flows, not
of identified institutional trades). Rendering: canvas/WebGL treemaps and grids with drill-down, tooltips, and
time scrubbing; precomputed per timeframe, refreshed on bar close.

## 8. Performance targets (S1)
Universe of 500 symbols, daily data, 20-node graph: under 2 s. 2,000 symbols, 10-year replay: under 60 s as a
background job. p95 interactive preview under 1 s on a sample.

## 9. Risks
Overfitting through repeated tweaking (surface the trial count), lookahead leaks (property-based tests), definitions
users disagree on (show definitions, allow edits), survivorship bias (point-in-time universes).
