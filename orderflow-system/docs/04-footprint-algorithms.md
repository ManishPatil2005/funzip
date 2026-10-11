# 04 · Footprint Algorithms (code: `ofx/orderflow/classify.py`, `footprint.py`)

## 1. Aggressor classification (decides data quality)
| Method | Rule | Quality |
|---|---|---|
| EXCHANGE | Feed flag (CME tag 5797; crypto taker side if present) | EXACT |
| QUOTE | price ≥ prevailing ask → ASK; ≤ bid → BID; strictly inside spread → UNKNOWN | ESTIMATED |
| TICK | price above previous → ASK; below → BID; equal → inherit last side | ESTIMATED |
| LEE_READY | Quote rule; midpoint trades fall back to tick rule | ESTIMATED |
| BAR | `split_bar_volume`: share to ask = (close−low)/(high−low); sums to bar volume | BAR_APPROXIMATED |
Details: prevailing quote found by bisect with optional `quote_lag`; locked/crossed quotes ignored; **unknown volume is never assigned to a side** (kept in `unknown_vol`). Why: a wrong side silently corrupts every delta downstream; an explicit unknown share is auditable.

## 2. Aggregation
Trades sorted by (ts, seq). Bar start = `floor((epoch − offset)/tf)·tf + offset` (offset aligns e.g. NSE 09:15 IST = 03:45 UTC for 30-min bars). Row = `round(price/tick)`. Per cell: `bid_vol` (sellers hit bid), `ask_vol` (buyers lifted offer), `unknown_vol`, trade counts.
- `delta = Σask − Σbid` ; `delta_min/max` = extremes of running delta inside the bar (shows intrabar swings).
- `poc_row` = max-volume row (ties → closest to bar centre). Bar `value_area(70%)` uses the Dalton two-row method (doc 05).
- Bar quality = EXACT only if every trade is exchange-flagged; otherwise ESTIMATED.

## 3. CVD
`cvd_close[n] = cvd_close[n−1] + delta[n]`, **reset at session change** (`apply_session_cvd`, key function per market: NSE session, MCX session, UTC day for crypto). Reason: carrying CVD across sessions makes the level meaningless; only slope within a session is used downstream.

## 4. Diagonal imbalance
For row r in a bar (rows outside the traded range are skipped because their zero is structural):
- **Ask imbalance** at r: `ask[r] ≥ ratio × bid[r−1]`.
- **Bid imbalance** at r: `bid[r] ≥ ratio × ask[r+1]`.
Filters: `min_volume`, `min_diff`, `ignore_zero` (an opposing zero otherwise counts as infinite ratio). Default ratio 3.0 (vendors differ: ATAS 1.5, TradingView 3.0 [doc 01]).
**Stacked** = ≥ `min_rows` (3) consecutive flagged rows, same side.
Edge cases: empty bars omitted; holes inside a bar count as zero; single-row bars yield none; trades with unknown side add volume but not to either side.
False-signal conditions: low-volume instruments (use `min_volume`), thin sessions, estimated side data (diagonal ratios amplify classification noise).
