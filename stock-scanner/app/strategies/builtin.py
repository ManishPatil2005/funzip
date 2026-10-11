"""Built-in strategies. Each evaluates the *latest completed bar* of a DataFrame."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from app.strategies import indicators as ind

BUY, SELL, NONE = "BUY", "SELL", "NONE"


@dataclass
class Result:
    signal: str = NONE
    reason: str = ""
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Strategy:
    id: str
    name: str
    category: str
    description: str
    params: dict[str, float]
    min_bars: Callable[[dict], int]
    func: Callable[..., Result]
    intraday_only: bool = False


REGISTRY: dict[str, Strategy] = {}


def strategy(id: str, name: str, category: str, description: str, params: dict, min_bars, intraday_only: bool = False):
    def deco(fn):
        REGISTRY[id] = Strategy(id, name, category, description, params, min_bars, fn, intraday_only)
        return fn

    return deco


def is_intraday(df: pd.DataFrame) -> bool:
    if len(df) < 3:
        return False
    return (df.index[-1] - df.index[-2]) < pd.Timedelta(hours=20)


def _r(x) -> float:
    return round(float(x), 4)


# ------------------------------------------------------------------- trend following
@strategy("ema_cross", "EMA Crossover", "Trend", "Fast EMA crosses the slow EMA.",
          {"fast": 9, "slow": 21}, lambda p: int(p["slow"]) + 5)
def ema_cross(df, fast=9, slow=21):
    f, s = ind.ema(df["close"], int(fast)), ind.ema(df["close"], int(slow))
    m = {"ema_fast": _r(f.iloc[-1]), "ema_slow": _r(s.iloc[-1])}
    if ind.crossed_above(f, s):
        return Result(BUY, f"EMA{int(fast)} crossed above EMA{int(slow)}", m)
    if ind.crossed_below(f, s):
        return Result(SELL, f"EMA{int(fast)} crossed below EMA{int(slow)}", m)
    return Result(NONE, "", m)


@strategy("golden_cross", "Golden / Death Cross", "Trend", "SMA 50 crosses SMA 200.",
          {"fast": 50, "slow": 200}, lambda p: int(p["slow"]) + 5)
def golden_cross(df, fast=50, slow=200):
    f, s = ind.sma(df["close"], int(fast)), ind.sma(df["close"], int(slow))
    m = {"sma_fast": _r(f.iloc[-1]), "sma_slow": _r(s.iloc[-1])}
    if ind.crossed_above(f, s):
        return Result(BUY, "Golden cross (fast SMA above slow SMA)", m)
    if ind.crossed_below(f, s):
        return Result(SELL, "Death cross (fast SMA below slow SMA)", m)
    return Result(NONE, "", m)


@strategy("macd_cross", "MACD Signal Cross", "Trend", "MACD line crosses its signal line.",
          {"fast": 12, "slow": 26, "signal": 9}, lambda p: int(p["slow"]) + int(p["signal"]) + 5)
def macd_cross(df, fast=12, slow=26, signal=9):
    line, sig, hist = ind.macd(df["close"], int(fast), int(slow), int(signal))
    m = {"macd": _r(line.iloc[-1]), "signal": _r(sig.iloc[-1]), "hist": _r(hist.iloc[-1])}
    if ind.crossed_above(line, sig):
        return Result(BUY, "MACD crossed above signal", m)
    if ind.crossed_below(line, sig):
        return Result(SELL, "MACD crossed below signal", m)
    return Result(NONE, "", m)


@strategy("supertrend", "Supertrend Flip", "Trend", "Supertrend changes direction.",
          {"period": 10, "mult": 3.0}, lambda p: int(p["period"]) + 5)
def supertrend_flip(df, period=10, mult=3.0):
    line, d = ind.supertrend(df, int(period), float(mult))
    m = {"supertrend": _r(line.iloc[-1]) if not np.isnan(line.iloc[-1]) else None, "direction": int(d.iloc[-1])}
    if d.iloc[-2] == -1 and d.iloc[-1] == 1:
        return Result(BUY, "Supertrend flipped to up-trend", m)
    if d.iloc[-2] == 1 and d.iloc[-1] == -1:
        return Result(SELL, "Supertrend flipped to down-trend", m)
    return Result(NONE, "", m)


@strategy("adx_di", "ADX Trend + DI Cross", "Trend", "+DI/-DI crossover while ADX confirms a trend.",
          {"period": 14, "threshold": 25}, lambda p: int(p["period"]) * 3)
def adx_di(df, period=14, threshold=25):
    a, pdi, mdi = ind.adx(df, int(period))
    m = {"adx": _r(a.iloc[-1]), "plus_di": _r(pdi.iloc[-1]), "minus_di": _r(mdi.iloc[-1])}
    if a.iloc[-1] >= threshold and ind.crossed_above(pdi, mdi):
        return Result(BUY, f"+DI crossed above -DI with ADX {a.iloc[-1]:.1f}", m)
    if a.iloc[-1] >= threshold and ind.crossed_below(pdi, mdi):
        return Result(SELL, f"-DI crossed above +DI with ADX {a.iloc[-1]:.1f}", m)
    return Result(NONE, "", m)


# ---------------------------------------------------------------------- breakouts
@strategy("donchian", "Donchian Breakout (Turtle)", "Breakout", "Close breaks the prior N-bar high or low.",
          {"period": 20}, lambda p: int(p["period"]) + 3)
def donchian_breakout(df, period=20):
    n = int(period)
    prior_hi = df["high"].iloc[-n - 1:-1].max()
    prior_lo = df["low"].iloc[-n - 1:-1].min()
    c = df["close"].iloc[-1]
    m = {"channel_high": _r(prior_hi), "channel_low": _r(prior_lo), "close": _r(c)}
    if c > prior_hi:
        return Result(BUY, f"Close above {n}-bar high", m)
    if c < prior_lo:
        return Result(SELL, f"Close below {n}-bar low", m)
    return Result(NONE, "", m)


@strategy("high52", "52-Week High/Low Breakout", "Breakout", "Daily close at a new 52-week extreme.",
          {"lookback": 250}, lambda p: int(p["lookback"]) + 2)
def high52(df, lookback=250):
    n = int(lookback)
    hi = df["close"].iloc[-n - 1:-1].max()
    lo = df["close"].iloc[-n - 1:-1].min()
    c = df["close"].iloc[-1]
    m = {"high": _r(hi), "low": _r(lo), "close": _r(c)}
    if c > hi:
        return Result(BUY, "New 52-week closing high", m)
    if c < lo:
        return Result(SELL, "New 52-week closing low", m)
    return Result(NONE, "", m)


@strategy("volume_breakout", "Volume Breakout", "Breakout", "Volume surge with a 20-bar price breakout.",
          {"period": 20, "volume_mult": 2.0}, lambda p: int(p["period"]) + 3)
def volume_breakout(df, period=20, volume_mult=2.0):
    n = int(period)
    avg_vol = df["volume"].iloc[-n - 1:-1].mean()
    prior_hi, prior_lo = df["high"].iloc[-n - 1:-1].max(), df["low"].iloc[-n - 1:-1].min()
    v, c = df["volume"].iloc[-1], df["close"].iloc[-1]
    ratio = v / avg_vol if avg_vol else 0
    m = {"volume_ratio": _r(ratio), "close": _r(c)}
    if avg_vol and ratio >= volume_mult:
        if c > prior_hi:
            return Result(BUY, f"Breakout on {ratio:.1f}x average volume", m)
        if c < prior_lo:
            return Result(SELL, f"Breakdown on {ratio:.1f}x average volume", m)
    return Result(NONE, "", m)


@strategy("bb_squeeze", "Bollinger Squeeze Breakout", "Breakout", "Low-volatility squeeze followed by a band break.",
          {"period": 20, "k": 2.0, "lookback": 120}, lambda p: int(p["lookback"]) + int(p["period"]))
def bb_squeeze(df, period=20, k=2.0, lookback=120):
    lo, mid, up = ind.bollinger(df["close"], int(period), float(k))
    width = (up - lo) / mid
    recent = width.iloc[-int(lookback):]
    squeezed = width.iloc[-2] <= recent.quantile(0.2)
    c = df["close"].iloc[-1]
    m = {"bandwidth": _r(width.iloc[-1]), "squeeze_prev_bar": bool(squeezed)}
    if squeezed and c > up.iloc[-1]:
        return Result(BUY, "Close above upper band after squeeze", m)
    if squeezed and c < lo.iloc[-1]:
        return Result(SELL, "Close below lower band after squeeze", m)
    return Result(NONE, "", m)


@strategy("inside_bar", "Inside Bar Breakout", "Breakout", "Close breaks the mother bar after an inside bar.",
          {}, lambda p: 4)
def inside_bar(df):
    mother, inside, last = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    is_inside = inside["high"] < mother["high"] and inside["low"] > mother["low"]
    m = {"mother_high": _r(mother["high"]), "mother_low": _r(mother["low"])}
    if is_inside and last["close"] > mother["high"]:
        return Result(BUY, "Broke above mother bar high", m)
    if is_inside and last["close"] < mother["low"]:
        return Result(SELL, "Broke below mother bar low", m)
    return Result(NONE, "", m)


@strategy("nr7", "NR7 Breakout", "Breakout", "Narrowest range of 7 bars followed by a breakout.",
          {}, lambda p: 10)
def nr7(df):
    rng = (df["high"] - df["low"])
    narrow = rng.iloc[-2] == rng.iloc[-8:-1].min()
    prev = df.iloc[-2]
    c = df["close"].iloc[-1]
    m = {"nr7_prev_bar": bool(narrow)}
    if narrow and c > prev["high"]:
        return Result(BUY, "Broke above NR7 bar high", m)
    if narrow and c < prev["low"]:
        return Result(SELL, "Broke below NR7 bar low", m)
    return Result(NONE, "", m)


# ------------------------------------------------------------------ mean reversion
@strategy("rsi_reversal", "RSI Reversal", "Mean Reversion", "RSI re-enters from oversold or overbought.",
          {"period": 14, "oversold": 30, "overbought": 70}, lambda p: int(p["period"]) * 3)
def rsi_reversal(df, period=14, oversold=30, overbought=70):
    r = ind.rsi(df["close"], int(period))
    m = {"rsi": _r(r.iloc[-1])}
    if r.iloc[-2] < oversold <= r.iloc[-1]:
        return Result(BUY, f"RSI recovered above {oversold}", m)
    if r.iloc[-2] > overbought >= r.iloc[-1]:
        return Result(SELL, f"RSI fell back below {overbought}", m)
    return Result(NONE, "", m)


@strategy("bb_reversion", "Bollinger Mean Reversion", "Mean Reversion", "Close returns inside a band after piercing it.",
          {"period": 20, "k": 2.0}, lambda p: int(p["period"]) + 3)
def bb_reversion(df, period=20, k=2.0):
    lo, mid, up = ind.bollinger(df["close"], int(period), float(k))
    c0, c1 = df["close"].iloc[-2], df["close"].iloc[-1]
    m = {"lower": _r(lo.iloc[-1]), "mid": _r(mid.iloc[-1]), "upper": _r(up.iloc[-1])}
    if c0 < lo.iloc[-2] and c1 >= lo.iloc[-1]:
        return Result(BUY, "Re-entered lower Bollinger band", m)
    if c0 > up.iloc[-2] and c1 <= up.iloc[-1]:
        return Result(SELL, "Re-entered upper Bollinger band", m)
    return Result(NONE, "", m)


@strategy("stochastic", "Stochastic Cross", "Mean Reversion", "%K crosses %D in oversold/overbought zones.",
          {"k": 14, "d": 3, "oversold": 20, "overbought": 80}, lambda p: int(p["k"]) + int(p["d"]) + 3)
def stochastic_cross(df, k=14, d=3, oversold=20, overbought=80):
    pk, pd_ = ind.stochastic(df, int(k), int(d))
    m = {"k": _r(pk.iloc[-1]), "d": _r(pd_.iloc[-1])}
    if ind.crossed_above(pk, pd_) and pk.iloc[-2] < oversold:
        return Result(BUY, "%K crossed above %D in oversold zone", m)
    if ind.crossed_below(pk, pd_) and pk.iloc[-2] > overbought:
        return Result(SELL, "%K crossed below %D in overbought zone", m)
    return Result(NONE, "", m)


# -------------------------------------------------------------- price action / intraday
@strategy("candle_engulfing", "Engulfing + Hammer Patterns", "Price Action",
          "Bullish/bearish engulfing and hammer/shooting-star candles.", {}, lambda p: 5)
def candle_patterns(df):
    p, c = df.iloc[-2], df.iloc[-1]
    body, rng = abs(c["close"] - c["open"]), c["high"] - c["low"]
    m = {"close": _r(c["close"])}
    bull_engulf = p["close"] < p["open"] and c["close"] > c["open"] and c["close"] >= p["open"] and c["open"] <= p["close"]
    bear_engulf = p["close"] > p["open"] and c["close"] < c["open"] and c["open"] >= p["close"] and c["close"] <= p["open"]
    lower = min(c["open"], c["close"]) - c["low"]
    upper = c["high"] - max(c["open"], c["close"])
    hammer = rng > 0 and body > 0 and lower >= 2 * body and upper <= 0.3 * body
    star = rng > 0 and body > 0 and upper >= 2 * body and lower <= 0.3 * body
    if bull_engulf:
        return Result(BUY, "Bullish engulfing", m)
    if bear_engulf:
        return Result(SELL, "Bearish engulfing", m)
    if hammer and p["close"] < p["open"]:
        return Result(BUY, "Hammer after a down bar", m)
    if star and p["close"] > p["open"]:
        return Result(SELL, "Shooting star after an up bar", m)
    return Result(NONE, "", m)


@strategy("gap", "Opening Gap", "Price Action", "Session opens with a gap versus the prior close.",
          {"gap_pct": 1.5}, lambda p: 3)
def gap(df, gap_pct=1.5):
    day = pd.Series(df.index.date, index=df.index)
    last_day = day.iloc[-1]
    prior = df[day < last_day]
    today = df[day == last_day]
    if prior.empty or today.empty:
        return Result(NONE, "Not enough sessions", {})
    pct = 100 * (today["open"].iloc[0] - prior["close"].iloc[-1]) / prior["close"].iloc[-1]
    m = {"gap_pct": _r(pct)}
    if pct >= gap_pct:
        return Result(BUY, f"Gap up {pct:.2f}%", m)
    if pct <= -gap_pct:
        return Result(SELL, f"Gap down {pct:.2f}%", m)
    return Result(NONE, "", m)


@strategy("vwap_reclaim", "VWAP Reclaim / Loss", "Intraday", "Price crosses session VWAP (use 5m/15m).",
          {}, lambda p: 10, intraday_only=True)
def vwap_reclaim(df):
    v = ind.vwap(df)
    m = {"vwap": _r(v.iloc[-1]), "close": _r(df["close"].iloc[-1])}
    if ind.crossed_above(df["close"], v):
        return Result(BUY, "Price reclaimed VWAP", m)
    if ind.crossed_below(df["close"], v):
        return Result(SELL, "Price lost VWAP", m)
    return Result(NONE, "", m)


@strategy("orb", "Opening Range Breakout", "Intraday", "Close breaks the first N-minute range (use 5m/15m).",
          {"minutes": 30}, lambda p: 6, intraday_only=True)
def orb(df, minutes=30):
    day = pd.Series(df.index.date, index=df.index)
    today = df[day == day.iloc[-1]]
    if len(today) < 3:
        return Result(NONE, "Session just started", {})
    step = (today.index[1] - today.index[0]).total_seconds() / 60
    bars = max(1, int(minutes // step))
    if len(today) <= bars:
        return Result(NONE, "Opening range still forming", {})
    opening = today.iloc[:bars]
    hi, lo, c = opening["high"].max(), opening["low"].min(), today["close"].iloc[-1]
    m = {"orb_high": _r(hi), "orb_low": _r(lo), "close": _r(c)}
    prev_c = today["close"].iloc[-2]
    if c > hi >= prev_c:
        return Result(BUY, f"Broke {int(minutes)}-minute opening range high", m)
    if c < lo <= prev_c:
        return Result(SELL, f"Broke {int(minutes)}-minute opening range low", m)
    return Result(NONE, "", m)


# ----------------------------------------------------------------------- execution
class StrategyError(ValueError):
    pass


def clean_params(strat: Strategy, overrides: dict | None) -> dict:
    params = dict(strat.params)
    for key, val in (overrides or {}).items():
        if key not in strat.params:
            raise StrategyError(f"Unknown parameter '{key}' for {strat.id}")
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise StrategyError(f"Parameter '{key}' must be a number")
        if not (0 < float(val) <= 1000):
            raise StrategyError(f"Parameter '{key}' out of range (0, 1000]")
        params[key] = val
    return params


def run_builtin(strat_id: str, df: pd.DataFrame, overrides: dict | None = None) -> Result:
    strat = REGISTRY.get(strat_id)
    if strat is None:
        raise StrategyError(f"Unknown strategy '{strat_id}'")
    params = clean_params(strat, overrides)
    if strat.intraday_only and not is_intraday(df):
        return Result(NONE, "Requires an intraday interval", {})
    need = strat.min_bars(params)
    if len(df) < need:
        return Result(NONE, f"Needs {need} bars, have {len(df)}", {})
    return strat.func(df, **params)


def catalogue() -> list[dict]:
    return [
        {"id": s.id, "name": s.name, "category": s.category, "description": s.description,
         "params": s.params, "intraday_only": s.intraday_only}
        for s in REGISTRY.values()
    ]
