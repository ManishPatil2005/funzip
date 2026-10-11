# Design

## 1. Principles
1. **Trust before beauty.** Show data identity, quality and freshness wherever a number appears.
2. **Explain, don't instruct.** Copy follows the language policy in RULES.md.
3. **One object, many views.** A scanner is a graph whether edited visually, generated from text or viewed as JSON.
4. **Progressive depth.** Learner sees plain language; professional opens definitions, parameters and raw data.
5. **Calm density.** Dense but scannable; no casino cues (no flashing P&L, no urgency prompts).

## 2. Information architecture
- **Workspace:** watchlists, chart, side panel (Context, Learn, Data).
- **Scanner:** builder, results, replay and export.
- **Backtest lab:** setup, runs, reports, comparisons.
- **Profile and Orderflow:** TPO, volume profile, footprint, CVD, with the Explain toggle.
- **Heatmaps:** market, sector, breadth, rotation, participation, liquidity.
- **Learn:** paths, lessons, journal.
- **Status:** feed health dashboard, data quality, quarantine inbox.
- **Settings:** providers (credentials via secure flow), plans, API keys, team.

## 3. Key screens

**Chart workspace.** Instrument badge (`NSE:EQ:RELIANCE | tick 0.05 | verified last 1,234.50`), feed pill
(`LIVE 120 ms` / `STALE 14 s, reconnecting` / `CLOSED`), data-quality chip for orderflow. Right panel tabs:
*Context* (auction, structure, liquidity, orderflow observations, risk areas, high/low participation areas),
*Learn* (concept cards for what is on the chart), *Data* (source, version, definitions).

**Scanner builder.** Condition cards in AND/OR/NOT groups with indentation and colour rails; live match count;
"why did this match?" drawer; version history; template gallery; natural language box above the canvas that fills
the same canvas ("explain back" step shown as editable cards).

**Backtest report.** Sections per BACKTEST_ENGINE §7; sensitivity heatmaps and Monte Carlo bands; a persistent
"Limitations" panel; trial count in the header.

**Feed status.** Table of providers and segments, state machine position, latency sparkline, subscription budget,
event log. Plain-language messages with the recovery plan and a manual "reconnect now" for admins.

**Quarantine inbox.** Series blocked by validation, ratio to anchor, probable cause (for example "looks like a x100
scale error"), actions: ignore, re-fetch, report.

## 4. Chart technology
- **TradingView Lightweight Charts** for candles, lines, histograms, crosshair and time scale [U: it supports
  custom series and primitives in recent versions; confirm the exact version's API].
- **Custom canvas layers** for TPO letters, footprint cells, volume profile, value area bands and annotations;
  level-of-detail so 10,000 cells stay at 60 fps.
- **Heatmaps:** canvas/WebGL treemap and grid components with virtualisation.
- Price axis is driven by validated data and the instrument's tick size; autoscale ignores quarantined or flagged
  outlier bars unless the user chooses to include them.

## 5. Visual system
Tokens as CSS variables with light and dark themes (system preference default). Neutral surfaces, one accent,
semantic colours for state; **not red/green alone**: use shape and text too (colour-blind safe). Monospaced tabular
numbers for prices. Spacing scale 4/8/12/16/24; type scale from 12 to 24; icons with labels.

TPO letter colours: a sequence validated for contrast in both themes (the current app's palette is the baseline).

## 6. Language and microcopy
Use the style guide in LEARNING_ENGINE §6. Examples:
- Yes: "Price is accepting above the prior value area. This is consistent with higher-auction participation."
- No: "Strong buy above 1,240."
Empty and error states explain cause and next step: "Angel feed reconnecting (attempt 3, retry in 8 s). Charts
show the last verified data from 10:41:07."

## 7. Accessibility and responsiveness
Keyboard navigation for every control; ARIA roles on custom canvases with text alternatives (summary tables);
focus management in drawers; reduced-motion respect; mobile layout for Learn, Status and read-only scans;
full workstation features on desktop.

## 8. Design deliverables to produce next
Design tokens file, component inventory, wireframes for the five key screens, a clickable prototype of the
scanner builder, and a usability test script (five traders of mixed experience).
