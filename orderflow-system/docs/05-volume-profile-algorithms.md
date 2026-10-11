# 05 · Volume Profile Algorithms (code: `volume_profile.py`, `common.py`)

**Build.** `from_trades`: `volume[row] += qty` (with ask/bid split kept). `from_candles` (when no ticks): spread each bar's volume over its rows — `uniform` or `close_weighted` (weight 1/(1+|row−close_row|)); result is flagged `approximated` and the UI must show it. Volume is conserved (tested).

**POC.** argmax of volume; ties → row closest to the profile centre (least biased).

**Value area (Dalton two-row method), 70%.** Start at POC with `acc = vol[POC]`. While `acc < 0.70·total`: sum the next **two rows above** and the next **two rows below**; absorb the heavier pair (ties go upward); at an edge absorb what remains. VAH/VAL = top/bottom rows included. Why two rows: Dalton's published procedure smooths single-row noise. Edge case: if one direction is exhausted the other is absorbed.

**HVN/LVN.** Smooth histogram with centred moving average (odd window, default 3). HVN = local maximum with prominence ≥ 15% of the smoothed peak; LVN = local minimum (not at profile edges) with prominence ≥ 15% of peak. Plateaus resolve to the midpoint. Parameters are explicit because "node" has no universal definition [I].

**Composite.** `merge` sums rows across sessions; mixed tick sizes are rejected (merging would misalign rows).

**Limits.** Profile from bars is shape-approximate; profile from estimated-side ticks has exact *volume* but estimated ask/bid split; session boundaries must be correct for session profiles.
