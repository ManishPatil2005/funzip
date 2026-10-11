"""Market Profile (TPO) engine following J. Dalton's auction-market concepts.

Concepts implemented (from *Mind Over Markets* / *Markets in Profile*):
  * 30-minute TPO periods, letters A..Z a..z, price rows at an auto-scaled tick
  * Point of Control (ties resolved toward the profile midpoint)
  * 70% Value Area using Dalton's two-rows-at-a-time expansion
  * Initial Balance (first hour), range extension, IB breakout
  * Open types: Open-Drive, Open-Test-Drive, Open-Rejection-Reverse, Open-Auction
  * Day types: Normal, Normal Variation, Trend, Double Distribution, Neutral,
    Neutral Extreme, Non-Trend
  * Profile shapes: P, b, D, B (double distribution), elongated
  * Excess vs poor highs/lows, single prints, naked (virgin) POCs
  * Multi-day context: value relationship, open location, the 80% rule

Every classifier is a documented *heuristic* with thresholds defined as
constants below. Dalton's day types are discretionary; treat the output as
decision support, not a guarantee.
"""
from __future__ import annotations

import math
import string
from dataclasses import dataclass

import pandas as pd

from app.data.universe import Instrument

LETTERS = string.ascii_uppercase + string.ascii_lowercase
SESSIONS = {"NSE": ("09:15", "15:30"), "MCX": ("09:00", "23:30")}

# ---- tunable thresholds -----------------------------------------------------
VALUE_AREA_PCT = 0.70
TARGET_ROWS = 50            # desired number of price rows when auto-selecting tick
TREND_EXT_RATIO = 1.0       # extension >= 1.0 x IB range  (=> day range >= 2 x IB)
TREND_CLOSE_ZONE = 0.20     # close within top/bottom 20% of the range
NEUTRAL_EXTREME_ZONE = 0.20
NON_TREND_RANGE_VS_AVG = 0.50
DRIVE_ZONE = 0.20           # open within 20% of period A range from the opposite extreme
TAIL_MIN_ROWS = 2           # >= 2 single-print rows at an extreme = excess tail
DD_MIN_GAP_ROWS = 3         # >= 3 consecutive thin rows between two nodes = double distribution
NICE_MULTIPLES = (1, 2, 4, 5, 10, 20, 40, 50, 100, 200, 400, 500, 1000)


class ProfileError(ValueError):
    pass


# ---- helpers ----------------------------------------------------------------
def nice_tick(price_range: float, base_tick: float, target_rows: int = TARGET_ROWS) -> float:
    raw = max(price_range / max(target_rows, 1), base_tick)
    for m in NICE_MULTIPLES:
        if base_tick * m >= raw:
            return round(base_tick * m, 10)
    return round(base_tick * NICE_MULTIPLES[-1], 10)


def _row(price: float, tick: float) -> int:
    return int(math.floor(price / tick + 1e-9))


def _price(idx: int, tick: float) -> float:
    return round(idx * tick, 8)


@dataclass
class Period:
    letter: str
    start: str
    open: float
    high: float
    low: float
    close: float


def split_sessions(df: pd.DataFrame, exchange: str) -> dict[str, pd.DataFrame]:
    start, end = SESSIONS.get(exchange, SESSIONS["NSE"])
    inside = df.between_time(start, end, inclusive="left")
    out: dict[str, pd.DataFrame] = {}
    for day, g in inside.groupby(inside.index.date):
        if len(g) >= 2:
            out[str(day)] = g
    return out


def to_periods(session: pd.DataFrame, exchange: str, period_minutes: int = 30) -> list[Period]:
    if period_minutes < 5:
        raise ProfileError("period_minutes must be at least 5")
    start_s = SESSIONS.get(exchange, SESSIONS["NSE"])[0]
    h, m = map(int, start_s.split(":"))
    origin = session.index[0].normalize() + pd.Timedelta(hours=h, minutes=m)
    minutes = ((session.index - origin).total_seconds() // 60).astype(int)
    bucket = minutes // period_minutes
    periods: list[Period] = []
    for n, (b, g) in enumerate(session.groupby(bucket)):
        if n >= len(LETTERS):
            break
        periods.append(Period(
            LETTERS[n], g.index[0].isoformat(), float(g["open"].iloc[0]), float(g["high"].max()),
            float(g["low"].min()), float(g["close"].iloc[-1]),
        ))
    return periods


def value_area(counts: list[int], poc_i: int, pct: float = VALUE_AREA_PCT) -> tuple[int, int]:
    """Dalton's method: from the POC compare the next two rows above vs below."""
    n, total = len(counts), sum(counts)
    lo = hi = poc_i
    acc = counts[poc_i]
    while acc < pct * total:
        can_up, can_dn = hi + 1 < n, lo - 1 >= 0
        if not can_up and not can_dn:
            break
        up = (counts[hi + 1] if can_up else 0) + (counts[hi + 2] if hi + 2 < n else 0)
        dn = (counts[lo - 1] if can_dn else 0) + (counts[lo - 2] if lo - 2 >= 0 else 0)
        if can_up and (up >= dn or not can_dn):
            hi, acc = min(hi + 2, n - 1), acc + up
        else:
            lo, acc = max(lo - 2, 0), acc + dn
    return lo, hi


# ---- classifiers ------------------------------------------------------------
def classify_open(periods: list[Period], prior: dict | None) -> dict:
    a = periods[0]
    open_ = a.open
    a_range = max(a.high - a.low, 1e-9)
    direction = 1 if a.close > open_ else -1 if a.close < open_ else 0
    b = periods[1] if len(periods) > 1 else None

    kind = "Open-Auction (in range)"
    if prior and (open_ > prior["high"] or open_ < prior["low"]):
        kind = "Open-Auction (out of range)"

    if direction != 0:
        from_open_opposite = (open_ - a.low) / a_range if direction == 1 else (a.high - open_) / a_range
        close_pos = (a.close - a.low) / a_range if direction == 1 else (a.high - a.close) / a_range
        held = True if b is None else (b.low >= open_ - 0.1 * a_range if direction == 1 else b.high <= open_ + 0.1 * a_range)
        opposite_exc = (open_ - a.low) / a_range if direction == 1 else (a.high - open_) / a_range
        beyond = abs(a.close - open_) / a_range
        if from_open_opposite <= DRIVE_ZONE and close_pos >= 1 - DRIVE_ZONE and held:
            kind = "Open-Drive"
        elif opposite_exc >= 0.15 and beyond >= 0.30 and (b is None or (b.close - open_) * direction > 0):
            kind = "Open-Test-Drive"

    if kind.startswith("Open-Auction") and b is not None:
        # Rejection-Reverse: the first move away from the open (period A) is rejected and the
        # initial-balance close ends on the other side of the open.
        ib_rng = max(max(a.high, b.high) - min(a.low, b.low), 1e-9)
        first_up, first_dn = a.high - open_, open_ - a.low
        first_dir = 1 if first_up > first_dn else -1
        first_exc = max(first_up, first_dn)
        final_dir = 1 if b.close > open_ else -1 if b.close < open_ else 0
        if final_dir and final_dir != first_dir and first_exc >= 0.25 * ib_rng \
                and abs(b.close - open_) >= 0.25 * ib_rng:
            kind = "Open-Rejection-Reverse"
            direction = final_dir
    label_dir = "up" if direction == 1 else "down" if direction == -1 else "flat"
    return {"type": kind, "direction": label_dir}


def tails_and_prints(counts: list[int], tick: float, low_idx: int) -> dict:
    n = len(counts)
    top = 0
    while top < n and counts[n - 1 - top] == 1:
        top += 1
    bottom = 0
    while bottom < n and counts[bottom] == 1:
        bottom += 1
    # interior single-print ranges (excluding the tails)
    ranges, start = [], None
    for i in range(bottom, n - top):
        if counts[i] == 1:
            start = i if start is None else start
        elif start is not None:
            ranges.append((start, i - 1))
            start = None
    if start is not None:
        ranges.append((start, n - top - 1))
    prints = [[_price(low_idx + a, tick), _price(low_idx + b + 1, tick)] for a, b in ranges if b - a + 1 >= 2]
    gap_rows = max((b - a + 1 for a, b in ranges), default=0)
    peak = max(counts)
    solid = max(3, 0.4 * peak)
    double = False
    for a, b in ranges:
        if b - a + 1 >= DD_MIN_GAP_ROWS and any(c >= solid for c in counts[:a]) and any(c >= solid for c in counts[b + 1:]):
            double = True
    return {"top_tail": top, "bottom_tail": bottom, "single_prints": prints, "double": double, "max_gap_rows": gap_rows}


def classify_day(ib_high, ib_low, high, low, close, tick, avg_range, double, n_periods) -> str:
    if n_periods < 3:
        return "Developing"
    day_range = max(high - low, 1e-9)
    ib_range = max(ib_high - ib_low, tick)
    tol = max(tick, 0.05 * ib_range)
    ext_up, ext_dn = max(0.0, high - ib_high), max(0.0, ib_low - low)
    up, dn = ext_up > tol, ext_dn > tol
    cp = (close - low) / day_range
    if double:
        return "Double Distribution"
    if up and dn:
        return "Neutral Extreme" if (cp >= 1 - NEUTRAL_EXTREME_ZONE or cp <= NEUTRAL_EXTREME_ZONE) else "Neutral"
    if up or dn:
        ext = ext_up if up else ext_dn
        near = cp >= 1 - TREND_CLOSE_ZONE if up else cp <= TREND_CLOSE_ZONE
        if ext / ib_range >= TREND_EXT_RATIO and near:
            return "Trend Day"
        return "Normal Variation"
    if avg_range and day_range < NON_TREND_RANGE_VS_AVG * avg_range:
        return "Non-Trend"
    return "Normal"


def classify_shape(counts: list[int], day_type: str, double: bool, tails: dict, tick: float) -> str:
    n = len(counts)
    if n < 4:
        return "Developing"
    if double:
        return "B (double distribution)"
    mass = sum(counts)
    centre = sum(i * c for i, c in enumerate(counts)) / mass / (n - 1)
    if day_type == "Trend Day":
        return "Elongated (trend)"
    if centre >= 0.62 and tails["bottom_tail"] >= TAIL_MIN_ROWS:
        return "P (short covering / buying)"
    if centre <= 0.38 and tails["top_tail"] >= TAIL_MIN_ROWS:
        return "b (long liquidation / selling)"
    if centre >= 0.60:
        return "P-like (upper-weighted)"
    if centre <= 0.40:
        return "b-like (lower-weighted)"
    return "D (balanced)"


# ---- core -------------------------------------------------------------------
def analyse_session(session: pd.DataFrame, inst: Instrument, tick: float, period_minutes: int = 30,
                    prior: dict | None = None, avg_range: float | None = None) -> dict:
    periods = to_periods(session, inst.exchange, period_minutes)
    if not periods:
        raise ProfileError("Session has no usable periods")
    high = max(p.high for p in periods)
    low = min(p.low for p in periods)
    low_idx, high_idx = _row(low, tick), _row(high, tick)
    n = high_idx - low_idx + 1
    if n > 2000:
        raise ProfileError("Tick size too small for this price range")
    letters: list[list[str]] = [[] for _ in range(n)]
    for p in periods:
        for r in range(_row(p.low, tick), _row(p.high, tick) + 1):
            letters[r - low_idx].append(p.letter)
    counts = [len(x) for x in letters]
    total = sum(counts)

    peak = max(counts)
    mid = (n - 1) / 2
    poc_i = min((i for i, c in enumerate(counts) if c == peak), key=lambda i: abs(i - mid))
    val_i, vah_i = value_area(counts, poc_i)

    tp = tails_and_prints(counts, tick, low_idx)
    ib_periods = periods[:2]
    ib_high, ib_low = max(p.high for p in ib_periods), min(p.low for p in ib_periods)
    close = periods[-1].close
    day_type = classify_day(ib_high, ib_low, high, low, close, tick, avg_range, tp["double"], len(periods))
    shape = classify_shape(counts, day_type, tp["double"], tp, tick)
    open_info = classify_open(periods, prior) if len(periods) >= 1 else {"type": "n/a", "direction": "flat"}

    top_count, bottom_count = counts[-1], counts[0]
    high_struct = "excess" if tp["top_tail"] >= TAIL_MIN_ROWS else "poor" if top_count >= 2 else "ok"
    low_struct = "excess" if tp["bottom_tail"] >= TAIL_MIN_ROWS else "poor" if bottom_count >= 2 else "ok"

    expected = math.ceil((pd.Timestamp("2000-01-01 " + SESSIONS[inst.exchange][1])
                          - pd.Timestamp("2000-01-01 " + SESSIONS[inst.exchange][0])).total_seconds() / 60 / period_minutes)
    rows = [{"price": _price(low_idx + i, tick), "letters": "".join(letters[i]), "count": counts[i]}
            for i in range(n - 1, -1, -1)]
    ib_range = max(ib_high - ib_low, tick)
    result = {
        "date": str(session.index[0].date()),
        "tick": tick, "period_minutes": period_minutes,
        "open": periods[0].open, "high": high, "low": low, "close": close,
        "periods": [p.__dict__ for p in periods],
        "periods_expected": expected, "complete": len(periods) >= expected,
        "rows": rows, "total_tpo": total,
        "poc": _price(low_idx + poc_i, tick),
        "vah": _price(low_idx + vah_i + 1, tick),  # top edge of the highest value row
        "val": _price(low_idx + val_i, tick),
        "ib": {"high": ib_high, "low": ib_low, "range": round(ib_range, 6),
               "ext_up": round(max(0.0, high - ib_high), 6), "ext_down": round(max(0.0, ib_low - low), 6)},
        "open_type": open_info, "day_type": day_type, "shape": shape,
        "high_structure": high_struct, "low_structure": low_struct,
        "tails": {"top": tp["top_tail"], "bottom": tp["bottom_tail"]},
        "single_prints": tp["single_prints"],
    }
    return result


def value_relationship(today: dict, prior: dict) -> str:
    if today["val"] >= prior["vah"]:
        return "higher"
    if today["vah"] <= prior["val"]:
        return "lower"
    if today["val"] >= prior["val"] and today["vah"] <= prior["vah"]:
        return "inside"
    if today["val"] <= prior["val"] and today["vah"] >= prior["vah"]:
        return "outside"
    mid_t, mid_p = (today["val"] + today["vah"]) / 2, (prior["val"] + prior["vah"]) / 2
    return "overlapping higher" if mid_t > mid_p else "overlapping lower"


def open_location(open_: float, prior: dict) -> str:
    if open_ > prior["high"]:
        return "above prior range"
    if open_ > prior["vah"]:
        return "above prior value"
    if open_ >= prior["val"]:
        return "inside prior value"
    if open_ >= prior["low"]:
        return "below prior value"
    return "below prior range"


def eighty_percent_rule(today: dict, prior: dict) -> dict:
    """Open outside prior value; two consecutive period closes back inside => rotate to the far side."""
    open_ = today["open"]
    out = {"applicable": False, "triggered": False}
    if prior["val"] <= open_ <= prior["vah"]:
        return out
    above = open_ > prior["vah"]
    out.update(applicable=True, direction="down" if above else "up",
               target=prior["val"] if above else prior["vah"])
    inside = [prior["val"] <= p["close"] <= prior["vah"] for p in today["periods"]]
    for i in range(1, len(inside)):
        if inside[i] and inside[i - 1]:
            out.update(triggered=True, trigger_period=today["periods"][i]["letter"])
            break
    return out


def naked_pocs(analyses: list[dict]) -> list[dict]:
    """POCs of earlier sessions that no later session has traded through."""
    found = []
    for i, a in enumerate(analyses[:-1] if len(analyses) > 1 else []):
        later = analyses[i + 1:]
        if not any(s["low"] <= a["poc"] <= s["high"] for s in later):
            found.append({"date": a["date"], "price": a["poc"]})
    return found


# ---- bias engine ------------------------------------------------------------
def bias(today: dict, prior: dict | None, rel: str | None, rule80: dict | None, naked: list[dict]) -> dict:
    score, reasons = 0.0, []
    close, poc, vah, val = today["close"], today["poc"], today["vah"], today["val"]

    def add(points: float, why: str):
        nonlocal score
        score += points
        reasons.append({"points": points, "why": why})

    if rel:
        table = {"higher": 2, "overlapping higher": 1, "lower": -2, "overlapping lower": -1}
        if rel in table:
            add(table[rel], f"Value area is {rel} vs prior session")
        else:
            reasons.append({"points": 0, "why": f"Value is {rel} relative to prior session (balance)"})
    if rule80 and rule80.get("applicable") and rule80.get("triggered"):
        pts = -2 if rule80["direction"] == "down" else 2
        add(pts, f"80% rule triggered: open outside prior value, re-accepted inside; target {rule80['target']:.2f}")
    if close > vah:
        add(2, "Price accepted above today's value area high")
    elif close < val:
        add(-2, "Price accepted below today's value area low")
    elif close >= poc:
        add(1, "Price above POC inside value")
    else:
        add(-1, "Price below POC inside value")
    ib = today["ib"]
    if ib["ext_up"] > 0 and close > ib["high"]:
        add(1, "Trading above Initial Balance high (range extension up)")
    if ib["ext_down"] > 0 and close < ib["low"]:
        add(-1, "Trading below Initial Balance low (range extension down)")
    ot = today["open_type"]
    sign = 1 if ot["direction"] == "up" else -1 if ot["direction"] == "down" else 0
    if ot["type"] == "Open-Drive":
        add(2 * sign, f"Open-Drive {ot['direction']}: strong initiative activity")
    elif ot["type"] == "Open-Test-Drive":
        add(1 * sign, f"Open-Test-Drive {ot['direction']}")
    elif ot["type"] == "Open-Rejection-Reverse":
        add(1 * sign, f"Open-Rejection-Reverse toward {ot['direction']}")
    if today["day_type"] == "Trend Day":
        add(2 if close >= (today["high"] + today["low"]) / 2 else -2, "Trend day: follow the direction, do not fade")
    if today["high_structure"] == "excess":
        add(-1, "Excess (single-print tail) at the high: rejection of higher prices")
    if today["low_structure"] == "excess":
        add(1, "Excess (single-print tail) at the low: rejection of lower prices")
    shape = today["shape"]
    if shape.startswith("P"):
        add(1, "P-shape profile: buying/short-covering")
    elif shape.startswith("b"):
        add(-1, "b-shape profile: liquidation/selling")

    notes = []
    if today["high_structure"] == "poor":
        notes.append("Poor high (no excess): unfinished business, often revisited")
    if today["low_structure"] == "poor":
        notes.append("Poor low (no excess): unfinished business, often revisited")
    for sp in today["single_prints"]:
        notes.append(f"Single prints {sp[0]:.2f}–{sp[1]:.2f}: fast-travel zone, often retested")
    for n in naked:
        notes.append(f"Naked POC {n['price']:.2f} from {n['date']}: acts as a magnet")
    if today["day_type"] in ("Normal", "Non-Trend"):
        notes.append(f"{today['day_type']} day: balance; fade the extremes toward POC rather than chase")

    signal = "BUY" if score >= 3 else "SELL" if score <= -3 else "NEUTRAL"
    return {"signal": signal, "score": score, "reasons": reasons, "notes": notes,
            "levels": trade_levels(today, prior, signal, naked)}


def trade_levels(today: dict, prior: dict | None, signal: str, naked: list[dict]) -> dict | None:
    if signal == "NEUTRAL":
        return None
    tick, price = today["tick"], today["close"]
    ib = today["ib"]
    structure = {today["poc"], today["vah"], today["val"], ib["high"], ib["low"]}
    targets = {today["high"], today["low"], ib["high"] + ib["range"], ib["low"] - ib["range"]}
    if prior:
        structure |= {prior["poc"], prior["vah"], prior["val"]}
        targets |= {prior["high"], prior["low"], prior["poc"], prior["vah"], prior["val"]}
    targets |= {n["price"] for n in naked}
    if signal == "BUY":
        below = sorted(p for p in structure if p < price - tick)
        above = sorted(p for p in targets if p > price + tick)
        stop = (below[-1] - tick) if below else price - ib["range"]
        t1 = above[0] if above else price + ib["range"]
        t2 = above[1] if len(above) > 1 else t1 + ib["range"]
    else:
        above_s = sorted(p for p in structure if p > price + tick)
        below_t = sorted((p for p in targets if p < price - tick), reverse=True)
        stop = (above_s[0] + tick) if above_s else price + ib["range"]
        t1 = below_t[0] if below_t else price - ib["range"]
        t2 = below_t[1] if len(below_t) > 1 else t1 - ib["range"]
    risk = abs(price - stop)
    rr = round(abs(t1 - price) / risk, 2) if risk else None
    return {"entry": round(price, 4), "stop": round(stop, 4), "target1": round(t1, 4),
            "target2": round(t2, 4), "risk_reward_t1": rr}


# ---- public report ----------------------------------------------------------
def build_report(df: pd.DataFrame, inst: Instrument, period_minutes: int = 30,
                 date: str | None = None, lookback: int = 6) -> dict:
    sessions = split_sessions(df, inst.exchange)
    if not sessions:
        raise ProfileError("No intraday sessions found. Use an interval of 30m or finer.")
    dates = sorted(sessions)
    if date:
        if date not in sessions:
            raise ProfileError(f"No session for {date}. Available: {dates[-10:]}")
        dates = [d for d in dates if d <= date]
    dates = dates[-max(2, lookback):]
    ranges = [float(sessions[d]["high"].max() - sessions[d]["low"].min()) for d in dates]
    ref_price = float(sessions[dates[-1]]["close"].iloc[-1])
    ordered = sorted(ranges)
    median_range = ordered[len(ordered) // 2]
    tick = nice_tick(median_range if median_range > 0 else ref_price * 0.01, inst.tick)

    analyses: list[dict] = []
    for i, d in enumerate(dates):
        prior = analyses[-1] if analyses else None
        avg = sum(ranges[:i]) / i if i else None
        analyses.append(analyse_session(sessions[d], inst, tick, period_minutes, prior, avg))
    today = analyses[-1]
    prior = analyses[-2] if len(analyses) > 1 else None
    rel = value_relationship(today, prior) if prior else None
    loc = open_location(today["open"], prior) if prior else None
    rule80 = eighty_percent_rule(today, prior) if prior else None
    naked = naked_pocs(analyses)
    decision = bias(today, prior, rel, rule80, naked)

    def brief(a):
        return {k: a[k] for k in ("date", "high", "low", "poc", "vah", "val", "day_type", "shape")}

    return {
        "symbol": inst.symbol, "exchange": inst.exchange, "proxy": inst.proxy,
        "profile": today, "prior": brief(prior) if prior else None,
        "history": [brief(a) for a in analyses[:-1]],
        "value_relationship": rel, "open_location": loc, "rule_80": rule80,
        "naked_pocs": naked, "bias": decision,
        "disclaimer": "Educational analysis based on heuristic Market Profile rules; not investment advice.",
    }


def render_ascii(profile: dict) -> str:
    lines = [f"{profile['date']}  POC {profile['poc']}  VA {profile['val']}–{profile['vah']}  "
             f"IB {profile['ib']['low']:.2f}–{profile['ib']['high']:.2f}"]
    for r in profile["rows"]:
        mark = ""
        if abs(r["price"] - profile["poc"]) < 1e-9:
            mark = " ◄ POC"
        in_va = profile["val"] <= r["price"] < profile["vah"]
        lines.append(f"{r['price']:>10.2f} {'│' if in_va else ' '} {r['letters']}{mark}")
    return "\n".join(lines)
