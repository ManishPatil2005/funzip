# 06 · Market Profile (TPO) Algorithms (code: `market_profile.py`)

**Fully implementable on any feed** — needs only price and time (candles suffice, no aggressor data).

**Sessions** (`SessionSpec`): NSE 09:15 IST + 6 h 15 m; MCX 09:00 IST + 14 h 30 m [session hours are my configuration, verify with exchange circulars — **U**]; crypto = UTC day. Candles outside a session are ignored.

**TPO build.** Period index = `floor((t − session_start)/period)`; letters A…Z, a…z by index. For each period, every row from its low to its high gets one TPO (letter). Candles must not be coarser than the period.

**Levels (`tpo_levels`).** POC = row with most TPOs (centre-biased ties). Value area = Dalton two-row method over TPO counts (70%). **Initial Balance** = range of the first two periods. **Single prints** = interior runs (≥ 2 rows) with count 1. **Tails** = single-count rows touching the high or low (reported as row counts).

**Composites.** `daily` merges sessions by local date; `weekly` merges by ISO week; letters are dropped on composites (they lose meaning). Mixed ticks rejected.

**Teaching hooks (descriptive only).** Profile shape (normal, P/b-shaped, double distribution), open relative to prior value area, and excess/tails are surfaced as observations with alternatives — never as instructions.

**Edge cases.** Gaps → counts of zero between rows (dense view fills zeros); single-period sessions give IB = that period; DST irrelevant for IST; holidays simply have no candles.
