"""User-defined strategies via a declarative rule DSL.

Rules are validated JSON evaluated by a fixed interpreter. No user input is ever
passed to eval/exec, so custom strategies cannot execute code.

Example:
{
  "name": "Trend pullback",
  "buy":  {"all": [
      {"left": {"field": "close"}, "op": ">", "right": {"ind": "ema", "period": 50}},
      {"left": {"ind": "rsi", "period": 14}, "op": "crosses_above", "right": {"value": 40}}]},
  "sell": {"any": [
      {"left": {"field": "close"}, "op": "<", "right": {"ind": "ema", "period": 50}}]}
}
"""
from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.strategies import indicators as ind
from app.strategies.builtin import BUY, NONE, SELL, Result

FIELDS = ("open", "high", "low", "close", "volume")
INDICATORS = (
    "sma", "ema", "rsi", "atr", "adx", "plus_di", "minus_di", "roc", "stoch_k", "stoch_d",
    "macd", "macd_signal", "macd_hist", "bb_upper", "bb_mid", "bb_lower", "supertrend",
    "donchian_high", "donchian_low", "vwap", "obv", "volume_sma", "highest_high", "lowest_low",
)
OPS = (">", "<", ">=", "<=", "crosses_above", "crosses_below")
INDICATORS_NO_PERIOD = {"vwap", "obv", "macd", "macd_signal", "macd_hist"}


class Operand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["open", "high", "low", "close", "volume"] | None = None
    ind: Literal[
        "sma", "ema", "rsi", "atr", "adx", "plus_di", "minus_di", "roc", "stoch_k", "stoch_d",
        "macd", "macd_signal", "macd_hist", "bb_upper", "bb_mid", "bb_lower", "supertrend",
        "donchian_high", "donchian_low", "vwap", "obv", "volume_sma", "highest_high", "lowest_low",
    ] | None = None
    period: int = Field(default=14, ge=1, le=400)
    value: float | None = Field(default=None, ge=-1e9, le=1e9)
    mult: float = Field(default=1.0, ge=-1000, le=1000)
    shift: int = Field(default=0, ge=0, le=20)

    @model_validator(mode="after")
    def exactly_one(self):
        if sum(x is not None for x in (self.field, self.ind, self.value)) != 1:
            raise ValueError("Operand needs exactly one of: field, ind, value")
        return self

    def label(self) -> str:
        if self.value is not None:
            core = f"{self.value:g}"
        elif self.field:
            core = self.field
        else:
            core = self.ind if self.ind in INDICATORS_NO_PERIOD else f"{self.ind}({self.period})"
        if self.mult != 1:
            core = f"{self.mult:g}×{core}"
        return f"{core}[-{self.shift}]" if self.shift else core


class Condition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    left: Operand
    op: Literal[">", "<", ">=", "<=", "crosses_above", "crosses_below"]
    right: Operand


class RuleGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: list[Condition] = Field(default_factory=list, max_length=10)
    any: list[Condition] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def not_empty(self):
        if not self.all and not self.any:
            raise ValueError("A rule group needs at least one condition in 'all' or 'any'")
        return self


class CustomStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    buy: RuleGroup | None = None
    sell: RuleGroup | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = v.strip()
        if not v or not all(ch.isalnum() or ch in " -_.()/+" for ch in v):
            raise ValueError("Name may contain letters, digits, spaces and - _ . ( ) / +")
        return v

    @model_validator(mode="after")
    def has_rule(self):
        if self.buy is None and self.sell is None:
            raise ValueError("Define at least a buy or a sell rule")
        return self


# ------------------------------------------------------------------- evaluation
def _series(df: pd.DataFrame, o: Operand, cache: dict) -> pd.Series:
    key = (o.field, o.ind, o.period, o.value, o.mult, o.shift)
    if key in cache:
        return cache[key]
    n = o.period
    if o.value is not None:
        s = pd.Series(o.value, index=df.index, dtype=float)
    elif o.field:
        s = df[o.field].astype(float)
    else:
        name = o.ind
        c = df["close"]
        if name == "sma": s = ind.sma(c, n)
        elif name == "ema": s = ind.ema(c, n)
        elif name == "rsi": s = ind.rsi(c, n)
        elif name == "atr": s = ind.atr(df, n)
        elif name == "adx": s = ind.adx(df, n)[0]
        elif name == "plus_di": s = ind.adx(df, n)[1]
        elif name == "minus_di": s = ind.adx(df, n)[2]
        elif name == "roc": s = ind.roc(c, n)
        elif name == "stoch_k": s = ind.stochastic(df, n)[0]
        elif name == "stoch_d": s = ind.stochastic(df, n)[1]
        elif name == "macd": s = ind.macd(c)[0]
        elif name == "macd_signal": s = ind.macd(c)[1]
        elif name == "macd_hist": s = ind.macd(c)[2]
        elif name == "bb_upper": s = ind.bollinger(c, n)[2]
        elif name == "bb_mid": s = ind.bollinger(c, n)[1]
        elif name == "bb_lower": s = ind.bollinger(c, n)[0]
        elif name == "supertrend": s = ind.supertrend(df, n)[0]
        elif name == "donchian_high": s = ind.donchian(df, n)[1].shift(1)
        elif name == "donchian_low": s = ind.donchian(df, n)[0].shift(1)
        elif name == "vwap": s = ind.vwap(df)
        elif name == "obv": s = ind.obv(df)
        elif name == "volume_sma": s = ind.sma(df["volume"], n)
        elif name == "highest_high": s = df["high"].rolling(n, min_periods=n).max().shift(1)
        elif name == "lowest_low": s = df["low"].rolling(n, min_periods=n).min().shift(1)
        else:  # pragma: no cover - pydantic Literal blocks this
            raise ValueError(f"Unknown indicator {name}")
    if o.shift:
        s = s.shift(o.shift)
    if o.mult != 1:
        s = s * o.mult
    cache[key] = s
    return s


def _eval_condition(df: pd.DataFrame, c: Condition, cache: dict) -> tuple[bool, str]:
    a, b = _series(df, c.left, cache), _series(df, c.right, cache)
    text = f"{c.left.label()} {c.op.replace('_', ' ')} {c.right.label()}"
    if len(a) < 2 or pd.isna(a.iloc[-1]) or pd.isna(b.iloc[-1]):
        return False, text
    x, y = a.iloc[-1], b.iloc[-1]
    if c.op == ">": ok = x > y
    elif c.op == "<": ok = x < y
    elif c.op == ">=": ok = x >= y
    elif c.op == "<=": ok = x <= y
    else:
        if pd.isna(a.iloc[-2]) or pd.isna(b.iloc[-2]):
            return False, text
        ok = (a.iloc[-2] <= b.iloc[-2] and x > y) if c.op == "crosses_above" else (a.iloc[-2] >= b.iloc[-2] and x < y)
    return bool(ok), text


def _eval_group(df: pd.DataFrame, g: RuleGroup, cache: dict) -> tuple[bool, list[str]]:
    all_res = [_eval_condition(df, c, cache) for c in g.all]
    any_res = [_eval_condition(df, c, cache) for c in g.any]
    ok = all(r[0] for r in all_res) if all_res else True
    if any_res:
        ok = ok and any(r[0] for r in any_res)
    reasons = [t for passed, t in all_res + any_res if passed]
    return ok, reasons


def evaluate(df: pd.DataFrame, strat: CustomStrategy) -> Result:
    if len(df) < 5:
        return Result(NONE, "Not enough data", {})
    cache: dict = {}
    metrics = {"close": round(float(df["close"].iloc[-1]), 4)}
    if strat.buy:
        ok, why = _eval_group(df, strat.buy, cache)
        if ok:
            return Result(BUY, " AND ".join(why) or "Buy rules satisfied", metrics)
    if strat.sell:
        ok, why = _eval_group(df, strat.sell, cache)
        if ok:
            return Result(SELL, " AND ".join(why) or "Sell rules satisfied", metrics)
    return Result(NONE, "", metrics)


def parse(payload: dict) -> CustomStrategy:
    return CustomStrategy.model_validate(payload)


TEMPLATES = [
    {
        "name": "Trend pullback (EMA50 + RSI)",
        "description": "Buy RSI recovery above 40 in an up-trend; sell on close below EMA50.",
        "buy": {"all": [
            {"left": {"field": "close"}, "op": ">", "right": {"ind": "ema", "period": 50}},
            {"left": {"ind": "rsi", "period": 14}, "op": "crosses_above", "right": {"value": 40}}]},
        "sell": {"any": [
            {"left": {"field": "close"}, "op": "<", "right": {"ind": "ema", "period": 50}}]},
    },
    {
        "name": "Volume thrust breakout",
        "description": "Close above 20-bar high on twice the average volume.",
        "buy": {"all": [
            {"left": {"field": "close"}, "op": ">", "right": {"ind": "highest_high", "period": 20}},
            {"left": {"field": "volume"}, "op": ">", "right": {"ind": "volume_sma", "period": 20, "mult": 2}}]},
        "sell": {"all": [
            {"left": {"field": "close"}, "op": "<", "right": {"ind": "lowest_low", "period": 20}},
            {"left": {"field": "volume"}, "op": ">", "right": {"ind": "volume_sma", "period": 20, "mult": 2}}]},
    },
]
