"""Order-flow pattern detectors.

Every detector returns `Observation`s: a description of what the data shows, how
trustworthy it is, what else could explain it, and where it breaks. None of them
returns a trade instruction. Thresholds are explicit parameters (no hidden magic).
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from ofx.domain import DataQuality, Trade, row_to_price, weakest
from ofx.orderflow.footprint import (
    FootprintBar,
    ImbalanceConfig,
    find_imbalances,
    stacked_imbalances,
)
from ofx.orderflow.observation import Observation, cap_confidence


# ------------------------------------------------------------------------ helpers
def pivots(values: Sequence[float], left: int, right: int, kind: Literal["high", "low"]) -> list[int]:
    """Confirmed pivot indices only.

    A pivot high at i is strictly above the `left` bars before it and >= the `right`
    bars after it. It is only reported once `right` later bars exist, so a pivot never
    appears and later disappears (no repainting).
    """
    if left < 1 or right < 1:
        raise ValueError("left and right must be >= 1")
    sign = 1.0 if kind == "high" else -1.0
    v = [sign * x for x in values]
    out = []
    for i in range(left, len(v) - right):
        if all(v[i] > v[i - k] for k in range(1, left + 1)) and all(v[i] >= v[i + k] for k in range(1, right + 1)):
            out.append(i)
    return out


def _quality(bars: Sequence[FootprintBar]) -> DataQuality:
    return weakest(*(b.quality for b in bars)) if bars else DataQuality.ESTIMATED


def _std(xs: Sequence[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def _percentile(xs: Sequence[float], pct: float) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    k = (len(s) - 1) * pct / 100.0
    lo, hi = int(math.floor(k)), int(math.ceil(k))
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _session_id(b: FootprintBar) -> float:
    """Bars of one session share the cvd_open == 0 chain; we detect resets in `_same_session`."""
    return b.cvd_open


def _same_session(bars: Sequence[FootprintBar], i: int, j: int) -> bool:
    """True when no CVD reset happened between bar i and bar j (a reset shows as a bar whose
    cvd_open is 0 while the previous bar's cvd_close is not)."""
    for k in range(i + 1, j + 1):
        if bars[k].cvd_open == 0.0 and bars[k - 1].cvd_close != 0.0:
            return False
    return True


# ------------------------------------------------------------------ delta divergence
def delta_divergence(
    bars: Sequence[FootprintBar], left: int = 2, right: int = 2, z_min: float = 1.0,
    max_unknown_share: float = 0.3, max_gap_bars: int = 40,
) -> list[Observation]:
    """Price extreme versus CVD at the same extremes.

    For consecutive confirmed pivot highs i<j with price_j > price_i, the CVD change is
    standardised: z = (cvd_j - cvd_i) / (sigma_delta * sqrt(k)), k = j - i. The sqrt(k) term
    is the random-walk scaling of a sum of k bar deltas, so z is comparable across spans.
    A divergence is reported when z <= -z_min (lows mirror it). Pairs across a CVD reset or
    with a high share of unknown-side volume are skipped.
    """
    obs: list[Observation] = []
    if len(bars) < left + right + 3:
        return obs
    sigma = _std([b.delta for b in bars])
    if sigma == 0:
        return obs
    for kind in ("high", "low"):
        series = [b.high_px if kind == "high" else b.low_px for b in bars]
        idx = pivots(series, left, right, kind)  # type: ignore[arg-type]
        for a, b_ in zip(idx, idx[1:]):
            k = b_ - a
            if k > max_gap_bars or not _same_session(bars, a, b_):
                continue
            span = bars[a:b_ + 1]
            if max(x.unknown_share for x in span) > max_unknown_share:
                continue
            higher = series[b_] > series[a] if kind == "high" else series[b_] < series[a]
            if not higher:
                continue
            z = (bars[b_].cvd_close - bars[a].cvd_close) / (sigma * math.sqrt(k))
            diverged = z <= -z_min if kind == "high" else z >= z_min
            if not diverged:
                continue
            q = _quality(span)
            conf = cap_confidence(min(1.0, abs(z) / (2 * z_min)), q)
            if kind == "high":
                text = (f"Price made a higher high ({series[a]:g} to {series[b_]:g}) while cumulative delta "
                        f"made a lower high (z={z:.2f}): the push higher had less net buyer-initiated volume behind it.")
                alts = ("Passive sellers absorbing buyers at the highs.", "Delta lag from side-classification error.",
                        "Trend continuation with delta catching up later.")
            else:
                text = (f"Price made a lower low ({series[a]:g} to {series[b_]:g}) while cumulative delta "
                        f"made a higher low (z={z:.2f}): the push lower had less net seller-initiated volume behind it.")
                alts = ("Passive buyers absorbing sellers at the lows.", "Delta lag from side-classification error.",
                        "Trend continuation with delta catching up later.")
            obs.append(Observation(
                kind=f"delta_divergence_{kind}", ts_start=bars[a].ts_open, ts_end=bars[b_].ts_close,
                summary=text, data_quality=q, method="cvd_pivot_compare_v1", confidence=conf,
                price_low=min(series[a], series[b_]), price_high=max(series[a], series[b_]),
                evidence={"z": round(z, 3), "bars_apart": k, "cvd_a": bars[a].cvd_close, "cvd_b": bars[b_].cvd_close,
                          "sigma_delta": round(sigma, 3)},
                alternatives=alts,
                limitations="Pivots are confirmed after the right-side bars; the pair is known only then. "
                            "Sample is small when few pivots exist.",
                teaching_ref="delta_divergence",
            ))
    return sorted(obs, key=lambda o: o.ts_end)


# ---------------------------------------------------------------------- absorption
def absorption(
    bars: Sequence[FootprintBar], lookback: int = 20, volume_pct: float = 80.0,
    max_efficiency: float = 0.6, min_delta_share: float = 0.2, max_progress: float = 0.35,
) -> list[Observation]:
    """Heavy one-sided aggression that produced little price progress.

    Conditions on bar i (all must hold): volume >= the `volume_pct` percentile of the
    previous `lookback` bars; body/range <= max_efficiency; |delta|/volume >= min_delta_share;
    progress in the direction of delta <= max_progress * range. Zero-range bars are skipped.
    """
    obs: list[Observation] = []
    for i in range(lookback, len(bars)):
        b = bars[i]
        v = b.volume
        rng = b.high_px - b.low_px
        if v <= 0 or rng <= 0 or b.unknown_share > 0.3:
            continue
        if v < _percentile([x.volume for x in bars[i - lookback:i]], volume_pct):
            continue
        body = b.close_px - b.open_px
        if abs(body) / rng > max_efficiency:
            continue
        d = b.delta
        if abs(d) / v < min_delta_share:
            continue
        direction = 1.0 if d > 0 else -1.0
        if direction * body > max_progress * rng:
            continue
        q = b.quality
        raw = min(1.0, (abs(d) / v) / (2 * min_delta_share))
        if d > 0:
            text = (f"Heavy buyer-initiated volume (delta {d:+.0f} on {v:.0f}) produced little upward progress "
                    f"(body {body:+g} of range {rng:g}): passive supply at these prices absorbed it.")
            alts = ("Large resting offers (possible iceberg).", "A pause before continuation.", "Side-classification noise.")
        else:
            text = (f"Heavy seller-initiated volume (delta {d:+.0f} on {v:.0f}) produced little downward progress "
                    f"(body {body:+g} of range {rng:g}): passive demand at these prices absorbed it.")
            alts = ("Large resting bids (possible iceberg).", "A pause before continuation.", "Side-classification noise.")
        obs.append(Observation(
            kind="absorption_ask_flow" if d > 0 else "absorption_bid_flow", ts_start=b.ts_open, ts_end=b.ts_close,
            summary=text, data_quality=q, method="volume_pct_efficiency_v1", confidence=cap_confidence(raw, q),
            price_low=b.low_px, price_high=b.high_px,
            evidence={"volume": v, "delta": d, "body": body, "range": rng, "delta_share": round(abs(d) / v, 3),
                      "volume_percentile_threshold": round(_percentile([x.volume for x in bars[i - lookback:i]], volume_pct), 2)},
            alternatives=alts,
            limitations="Absorption is inferred from outcome (volume without progress); resting orders are not observed directly.",
            teaching_ref="absorption",
        ))
    return obs


# --------------------------------------------------------------------- exhaustion
def exhaustion(
    bars: Sequence[FootprintBar], lookback: int = 10, thin_share: float = 0.10, fade: float = 0.5, min_flags: int = 2,
) -> list[Observation]:
    """New extreme with signs that aggression faded there.

    Flags at a new top (bottoms mirror): (1) finished print: zero ask volume on the top row;
    (2) thin extreme: top two rows carry <= thin_share of bar volume; (3) delta fade: bar delta
    <= fade * previous bar delta while the previous delta had the same sign as the move.
    Reported when at least min_flags hold.
    """
    obs: list[Observation] = []
    for i in range(max(lookback, 1), len(bars)):
        b, prev = bars[i], bars[i - 1]
        window = bars[i - lookback:i]
        for side in ("top", "bottom"):
            if side == "top":
                if b.high_px <= max(x.high_px for x in window):
                    continue
                rows = [b.high_row, b.high_row - 1]
                extreme = b.rows[b.high_row]
                finished = extreme.ask_vol == 0 and extreme.bid_vol > 0
                sign = 1.0
            else:
                if b.low_px >= min(x.low_px for x in window):
                    continue
                rows = [b.low_row, b.low_row + 1]
                extreme = b.rows[b.low_row]
                finished = extreme.bid_vol == 0 and extreme.ask_vol > 0
                sign = -1.0
            v = b.volume
            if v <= 0:
                continue
            thin = sum(b.rows[r].volume for r in rows if r in b.rows) / v <= thin_share
            faded = sign * prev.delta > 0 and sign * b.delta <= fade * sign * prev.delta
            flags = [n for n, ok in (("finished_print", finished), ("thin_extreme", thin), ("delta_fade", faded)) if ok]
            if len(flags) < min_flags:
                continue
            q = b.quality
            conf = cap_confidence(len(flags) / 3.0, q)
            px = b.high_px if side == "top" else b.low_px
            text = (f"New {'high' if side == 'top' else 'low'} at {px:g} with {len(flags)} of 3 fade signs "
                    f"({', '.join(flags)}): aggression looked weaker at the extreme than earlier in the move.")
            obs.append(Observation(
                kind=f"exhaustion_{side}", ts_start=b.ts_open, ts_end=b.ts_close, summary=text, data_quality=q,
                method="extreme_flags_v1", confidence=conf, price_low=b.low_px, price_high=b.high_px,
                evidence={"flags": flags, "delta": b.delta, "prev_delta": prev.delta, "lookback": lookback},
                alternatives=("Momentum can continue after a thin extreme.", "A brief pause inside a larger trend.",
                              "Thin prints can reflect a low-liquidity period."),
                limitations="Flags are descriptive; each has false positives in fast markets and thin sessions.",
                teaching_ref="exhaustion",
            ))
    return obs


# ------------------------------------------------------------------ liquidity sweep
@dataclass(frozen=True)
class _Level:
    kind: Literal["high", "low"]
    price: float
    confirmed_at: int
    touches: int


def _levels(bars: Sequence[FootprintBar], left: int, right: int, tol: float) -> list[_Level]:
    """Pivot levels built causally: a level only counts earlier pivots as touches, so nothing
    that happens after the level is confirmed can change it (no look-ahead)."""
    out: list[_Level] = []
    for kind in ("high", "low"):
        series = [b.high_px if kind == "high" else b.low_px for b in bars]
        idx = pivots(series, left, right, kind)  # type: ignore[arg-type]
        for n, i in enumerate(idx):
            near = [j for j in idx[:n] if abs(series[j] - series[i]) <= tol]
            group = near + [i]
            price = max(series[j] for j in group) if kind == "high" else min(series[j] for j in group)
            out.append(_Level(kind, price, i + right, len(group)))  # type: ignore[arg-type]
    return sorted(out, key=lambda lv: lv.confirmed_at)


def liquidity_sweep(
    bars: Sequence[FootprintBar], tick: float, left: int = 3, right: int = 3, equal_tol_ticks: int = 2,
    min_excursion_ticks: int = 1, reclaim_bars: int = 3,
) -> list[Observation]:
    """Pierce of a prior pivot level followed by a close back inside (sweep) or not (acceptance).

    Equal highs/lows within equal_tol_ticks form one level. A breach needs at least
    min_excursion_ticks beyond the level. If a close returns inside within reclaim_bars bars
    (including the breach bar) it is a sweep; if not, price accepted beyond the level.
    Breaches too near the end of data to decide are not reported.
    """
    obs: list[Observation] = []
    seen: set[tuple[str, int]] = set()  # one event per (side, breach bar)
    for lv in _levels(bars, left, right, equal_tol_ticks * tick):
        for j in range(lv.confirmed_at + 1, len(bars)):
            b = bars[j]
            beyond = (b.high_px - lv.price) if lv.kind == "high" else (lv.price - b.low_px)
            if beyond < min_excursion_ticks * tick - 1e-12:
                continue
            if (lv.kind, j) in seen:
                break
            window = bars[j:j + reclaim_bars]
            if len(window) < reclaim_bars:
                break
            seen.add((lv.kind, j))
            reclaimed = any((w.close_px < lv.price) if lv.kind == "high" else (w.close_px > lv.price) for w in window)
            excursion = max(((w.high_px - lv.price) if lv.kind == "high" else (lv.price - w.low_px)) for w in window) / tick
            vol = dlt = 0.0
            lvl_row = round(lv.price / tick)
            for w in window:
                for r, c in w.rows.items():
                    if (r > lvl_row) if lv.kind == "high" else (r < lvl_row):
                        vol += c.volume
                        dlt += c.delta
            q = _quality(window)
            equal = " (equal-level cluster)" if lv.touches > 1 else ""
            side = "highs" if lv.kind == "high" else "lows"
            if reclaimed:
                text = (f"Price traded {excursion:.0f} ticks beyond prior {side}{equal} at {lv.price:g} and closed back inside "
                        f"within {reclaim_bars} bars; {vol:.0f} volume traded beyond the level (delta {dlt:+.0f}).")
                kind, conf_raw = f"liquidity_sweep_{lv.kind}", min(1.0, 0.4 + 0.1 * lv.touches + 0.05 * excursion)
                alts = ("Breakout attempt that failed for other reasons.", "Stop-run interpretation is an inference; orders are not visible.")
            else:
                text = (f"Price traded {excursion:.0f} ticks beyond prior {side}{equal} at {lv.price:g} and stayed beyond it "
                        f"for {reclaim_bars} bars: acceptance beyond the level rather than a quick return.")
                kind, conf_raw = f"acceptance_beyond_{lv.kind}", min(1.0, 0.4 + 0.1 * lv.touches)
                alts = ("Late reversal after the window.", "Trend continuation.")
            obs.append(Observation(
                kind=kind, ts_start=b.ts_open, ts_end=window[-1].ts_close, summary=text, data_quality=q,
                method="pivot_breach_reclaim_v1", confidence=cap_confidence(conf_raw, q),
                price_low=min(lv.price, b.low_px), price_high=max(lv.price, b.high_px),
                evidence={"level": lv.price, "touches": lv.touches, "excursion_ticks": excursion,
                          "volume_beyond": vol, "delta_beyond": dlt, "reclaim_bars": reclaim_bars},
                alternatives=alts,
                limitations="The level is a prior pivot, not a known order cluster; reclaim window is a parameter.",
                teaching_ref="liquidity_sweep",
            ))
            break  # one event per level
    return sorted(obs, key=lambda o: o.ts_start)


# ---------------------------------------------------------------- imbalance cluster
def imbalance_clusters(
    bars: Sequence[FootprintBar], cfg: ImbalanceConfig = ImbalanceConfig(), min_rows: int = 3, max_gap_bars: int = 10,
) -> list[Observation]:
    """Stacked-imbalance zones merged across nearby bars, with retest status.

    Zones of the same side that overlap in rows and occur within max_gap_bars merge. Status:
    'untested' (no later bar overlapped the zone), 'retested' (a later bar overlapped it and
    closed outside), 'traded_through' (a later bar closed beyond the far edge).
    """
    zones: list[dict] = []
    for i, b in enumerate(bars):
        for s in stacked_imbalances(find_imbalances(b, cfg), min_rows):
            for z in zones:
                if z["side"] == s.side and i - z["last"] <= max_gap_bars and s.low_row <= z["hi"] and s.high_row >= z["lo"]:
                    z["lo"], z["hi"], z["last"] = min(z["lo"], s.low_row), max(z["hi"], s.high_row), i
                    z["n"] += 1
                    break
            else:
                zones.append({"side": s.side, "lo": s.low_row, "hi": s.high_row, "first": i, "last": i, "n": 1})
    obs: list[Observation] = []
    tick = bars[0].tick if bars else 1.0
    for z in zones:
        lo_px, hi_px = row_to_price(z["lo"], tick), row_to_price(z["hi"], tick)
        status = "untested"
        for w in bars[z["last"] + 1:]:
            if w.low_row <= z["hi"] and w.high_row >= z["lo"]:
                status = "retested"
            beyond = w.close_px < lo_px if z["side"] == "ask" else w.close_px > hi_px
            if beyond and status == "retested":
                status = "traded_through"
                break
        span = bars[z["first"]:z["last"] + 1]
        q = _quality(span)
        who = "buyer-initiated" if z["side"] == "ask" else "seller-initiated"
        text = (f"{who.capitalize()} stacked imbalance zone {lo_px:g}-{hi_px:g} ({z['hi'] - z['lo'] + 1} rows, "
                f"{z['n']} bar(s) contributed); status: {status.replace('_', ' ')}.")
        obs.append(Observation(
            kind=f"imbalance_cluster_{z['side']}", ts_start=bars[z["first"]].ts_open, ts_end=bars[z["last"]].ts_close,
            summary=text, data_quality=q, method="stacked_diagonal_merge_v1",
            confidence=cap_confidence(min(1.0, 0.4 + 0.15 * z["n"]), q), price_low=lo_px, price_high=hi_px,
            evidence={"side": z["side"], "rows": z["hi"] - z["lo"] + 1, "bars": z["n"], "status": status,
                      "ratio": cfg.ratio},
            alternatives=("Zones can be ignored by price; a retest alone shows nothing about direction.",),
            limitations="Ratio and minimum volume are tunable; low-volume instruments produce noisy zones.",
            teaching_ref="stacked_imbalance",
        ))
    return obs


# ------------------------------------------------------------------------ CVD trend
def _theil_sen(y: Sequence[float]) -> float:
    n = len(y)
    slopes = [(y[j] - y[i]) / (j - i) for i in range(n) for j in range(i + 1, n)]
    slopes.sort()
    m = len(slopes)
    return 0.0 if m == 0 else (slopes[m // 2] if m % 2 else (slopes[m // 2 - 1] + slopes[m // 2]) / 2)


def _kendall_tau(y: Sequence[float]) -> float:
    n = len(y)
    if n < 2:
        return 0.0
    s = sum((y[j] > y[i]) - (y[j] < y[i]) for i in range(n) for j in range(i + 1, n))
    return s / (n * (n - 1) / 2)


def cvd_trend(bars: Sequence[FootprintBar], window: int = 20, tau_min: float = 0.3) -> Observation | None:
    """Classify the last `window` bars of one session: CVD versus price.

    Slopes use Theil-Sen (median of pairwise slopes: robust to one large bar); significance
    uses Kendall's tau (rank correlation with time). Classes: aligned, diverging,
    flow_without_progress, price_without_flow, balanced.
    """
    if len(bars) < window:
        return None
    span = list(bars[-window:])
    if not _same_session(span, 0, len(span) - 1):
        return None
    cvd = [b.cvd_close for b in span]
    px = [b.close_px for b in span]
    tau_c, tau_p = _kendall_tau(cvd), _kendall_tau(px)
    mean_v = sum(b.volume for b in span) / len(span)
    slope = _theil_sen(cvd) / mean_v if mean_v else 0.0
    c_sig, p_sig = abs(tau_c) >= tau_min, abs(tau_p) >= tau_min
    if c_sig and p_sig:
        cls = "aligned" if tau_c * tau_p > 0 else "diverging"
    elif c_sig:
        cls = "flow_without_progress"
    elif p_sig:
        cls = "price_without_flow"
    else:
        cls = "balanced"
    texts = {
        "aligned": "Cumulative delta and price trended the same way over the window.",
        "diverging": "Cumulative delta and price trended in opposite directions over the window.",
        "flow_without_progress": "Cumulative delta trended while price made no clear progress.",
        "price_without_flow": "Price trended while cumulative delta showed no clear trend.",
        "balanced": "Neither cumulative delta nor price showed a clear trend over the window.",
    }
    q = _quality(span)
    conf = cap_confidence(max(abs(tau_c), abs(tau_p)), q)
    return Observation(
        kind=f"cvd_trend_{cls}", ts_start=span[0].ts_open, ts_end=span[-1].ts_close,
        summary=f"{texts[cls]} (CVD tau {tau_c:+.2f}, price tau {tau_p:+.2f}).", data_quality=q,
        method="theil_sen_kendall_v1", confidence=conf,
        price_low=min(b.low_px for b in span), price_high=max(b.high_px for b in span),
        evidence={"class": cls, "tau_cvd": round(tau_c, 3), "tau_price": round(tau_p, 3),
                  "cvd_slope_per_mean_volume": round(slope, 4), "window": window},
        alternatives=("A short window can show a trend that a longer one does not.",),
        limitations="CVD level depends on the session reset point; only the slope is used.",
        teaching_ref="cvd_trend",
    )


# ------------------------------------------------------------------- large prints
def large_trades(trades: Sequence[Trade], pct: float = 99.0, min_qty: float = 0.0) -> list[Trade]:
    """Prints at or above the pct percentile of quantity (and min_qty). A threshold relative to
    the sample keeps the definition meaningful across instruments."""
    if not trades:
        return []
    cut = max(_percentile([t.qty for t in trades], pct), min_qty)
    return [t for t in trades if t.qty >= cut]
