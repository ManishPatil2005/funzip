import numpy as np
import pandas as pd
import pytest

from app.strategies import builder, indicators as ind
from app.strategies.builtin import BUY, NONE, REGISTRY, SELL, StrategyError, run_builtin


def frame(closes, spread=0.5, vol=1000):
    idx = pd.bdate_range("2026-01-01", periods=len(closes), tz="Asia/Kolkata")
    c = pd.Series(closes, index=idx, dtype=float)
    return pd.DataFrame({"open": c.shift(1).fillna(c.iloc[0]), "high": c + spread, "low": c - spread,
                         "close": c, "volume": float(vol)}, index=idx)


def test_sma_and_ema_known_values():
    s = pd.Series([1, 2, 3, 4, 5], dtype=float)
    assert ind.sma(s, 3).iloc[-1] == 4.0
    assert np.isnan(ind.sma(s, 3).iloc[1])
    assert ind.ema(s, 3).iloc[-1] == pytest.approx(4.0625, rel=1e-3)


def test_rsi_bounds_and_extremes():
    up = pd.Series(np.arange(1, 60, dtype=float))
    assert ind.rsi(up, 14).iloc[-1] == 100.0
    down = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert ind.rsi(down, 14).iloc[-1] < 1
    r = ind.rsi(pd.Series(np.random.default_rng(1).normal(100, 2, 200)), 14).dropna()
    assert r.between(0, 100).all()


def test_supertrend_direction_follows_trend():
    df = frame(list(np.linspace(100, 160, 60)))
    _, d = ind.supertrend(df, 10, 3.0)
    assert d.iloc[-1] == 1
    df = frame(list(np.linspace(160, 100, 60)))
    _, d = ind.supertrend(df, 10, 3.0)
    assert d.iloc[-1] == -1


def test_ema_cross_buy_and_sell():
    rising = frame([100] * 40 + [100, 101, 103, 106, 110, 115])
    assert run_builtin("ema_cross", rising, {"fast": 3, "slow": 8}).signal in (BUY, NONE)
    closes = [100] * 40 + [101, 103, 106, 110, 115, 121, 128]
    res = [run_builtin("ema_cross", frame(closes[:n]), {"fast": 3, "slow": 8}).signal for n in range(41, len(closes) + 1)]
    assert BUY in res
    down = [130] * 40 + [129, 127, 124, 120, 115, 109, 102]
    res = [run_builtin("ema_cross", frame(down[:n]), {"fast": 3, "slow": 8}).signal for n in range(41, len(down) + 1)]
    assert SELL in res


def test_donchian_breakout_detects_new_high_only_on_break():
    base = [100 + (i % 3) for i in range(30)]
    assert run_builtin("donchian", frame(base), {"period": 20}).signal == NONE
    assert run_builtin("donchian", frame(base + [120]), {"period": 20}).signal == BUY
    assert run_builtin("donchian", frame(base + [80]), {"period": 20}).signal == SELL


def test_insufficient_bars_returns_none_not_error():
    res = run_builtin("golden_cross", frame([100] * 30))
    assert res.signal == NONE and "Needs" in res.reason


def test_intraday_only_strategies_skip_daily_data():
    assert run_builtin("orb", frame([100] * 30)).reason == "Requires an intraday interval"


def test_unknown_strategy_and_bad_params_rejected():
    with pytest.raises(StrategyError):
        run_builtin("nope", frame([100] * 30))
    with pytest.raises(StrategyError):
        run_builtin("ema_cross", frame([100] * 30), {"bogus": 1})
    with pytest.raises(StrategyError):
        run_builtin("ema_cross", frame([100] * 30), {"fast": -5})
    with pytest.raises(StrategyError):
        run_builtin("ema_cross", frame([100] * 30), {"fast": "9; import os"})


def test_every_builtin_runs_on_daily_data():
    from app.data.provider import SyntheticProvider
    from app.data.universe import INSTRUMENTS

    df = SyntheticProvider().history(INSTRUMENTS["TCS"], "1d", "2y")
    for sid in REGISTRY:
        assert run_builtin(sid, df).signal in (BUY, SELL, NONE)


# ----------------------------------------------------------- custom rule builder
RULE = {
    "name": "Test rule",
    "buy": {"all": [{"left": {"field": "close"}, "op": ">", "right": {"ind": "sma", "period": 5}}]},
}


def test_builder_evaluates_simple_rule():
    strat = builder.parse(RULE)
    assert builder.evaluate(frame(list(range(100, 130))), strat).signal == BUY
    assert builder.evaluate(frame(list(range(130, 100, -1))), strat).signal == NONE


def test_builder_crosses_and_multiplier_and_shift():
    cross = builder.parse({"name": "x", "buy": {"all": [
        {"left": {"field": "close"}, "op": "crosses_above", "right": {"value": 110}}]}})
    assert builder.evaluate(frame([100] * 20 + [105, 111]), cross).signal == BUY
    assert builder.evaluate(frame([100] * 20 + [111, 112]), cross).signal == NONE
    vol = builder.parse({"name": "v", "buy": {"all": [
        {"left": {"field": "volume"}, "op": ">", "right": {"ind": "volume_sma", "period": 5, "mult": 2}}]}})
    df = frame([100] * 20)
    df.iloc[-1, df.columns.get_loc("volume")] = 5000
    assert builder.evaluate(df, vol).signal == BUY


@pytest.mark.parametrize("payload", [
    {"name": "a"},                                                        # no rules
    {"name": "a", "buy": {"all": []}},                                    # empty group
    {"name": "<script>", "buy": RULE["buy"]},                             # bad name chars
    {"name": "a", "buy": RULE["buy"], "extra": 1},                        # unknown key
    {"name": "a", "buy": {"all": [{"left": {"field": "close"}, "op": "==", "right": {"value": 1}}]}},
    {"name": "a", "buy": {"all": [{"left": {"ind": "__import__('os')"}, "op": ">", "right": {"value": 1}}]}},
    {"name": "a", "buy": {"all": [{"left": {"ind": "sma", "period": 100000}, "op": ">", "right": {"value": 1}}]}},
    {"name": "a", "buy": {"all": [{"left": {"field": "close", "value": 1}, "op": ">", "right": {"value": 1}}]}},
])
def test_builder_rejects_malicious_or_malformed_definitions(payload):
    with pytest.raises(Exception):
        builder.parse(payload)


def test_builder_condition_limit():
    cond = RULE["buy"]["all"][0]
    with pytest.raises(Exception):
        builder.parse({"name": "a", "buy": {"all": [cond] * 11}})


def test_templates_are_valid():
    for t in builder.TEMPLATES:
        builder.parse(t)
