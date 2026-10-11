from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from ofx.domain import DataQuality as Q
from ofx.main import create_app
from ofx.orderflow.observation import Observation
from ofx.strategy import EXAMPLE_RULES, SpecError, evaluate, parse_rule

T0 = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
BAR = timedelta(minutes=5)


def ob(kind, i, conf=0.8, q=Q.EXACT):
    return Observation(kind, T0 + BAR * i, T0 + BAR * (i + 1), "a context note", q, "m", conf)


RULE = {"name": "r", "window_bars": 3, "all_of": [{"kind": "liquidity_sweep_*"}, {"kind": "cvd_trend_diverging"}], "teaching_note": "study it"}


def test_match_when_conditions_coincide_and_quality_is_weakest():
    m = evaluate(parse_rule(RULE), [ob("liquidity_sweep_low", 2), ob("cvd_trend_diverging", 4, 0.5, Q.ESTIMATED)], BAR)
    assert len(m) == 1 and m[0].data_quality is Q.ESTIMATED and m[0].confidence <= 0.5 and len(m[0].evidence) == 2


def test_no_match_outside_window_or_with_none_of():
    far = [ob("liquidity_sweep_low", 2), ob("cvd_trend_diverging", 20)]
    assert evaluate(parse_rule(RULE), far, BAR) == []
    r = parse_rule({**RULE, "none_of": [{"kind": "exhaustion_*"}]})
    assert evaluate(r, [ob("liquidity_sweep_low", 2), ob("cvd_trend_diverging", 3), ob("exhaustion_top", 3)], BAR) == []


def test_min_confidence_and_quality_filters():
    r = parse_rule({**RULE, "all_of": [{"kind": "liquidity_sweep_*", "min_confidence": 0.9}, {"kind": "cvd_trend_diverging"}]})
    assert evaluate(r, [ob("liquidity_sweep_low", 2, 0.5), ob("cvd_trend_diverging", 3)], BAR) == []
    r2 = parse_rule({**RULE, "all_of": [{"kind": "liquidity_sweep_*", "quality_at_least": "exact"}, {"kind": "cvd_trend_diverging"}]})
    assert evaluate(r2, [ob("liquidity_sweep_low", 2, 0.5, Q.ESTIMATED), ob("cvd_trend_diverging", 3)], BAR) == []


@pytest.mark.parametrize("bad", [
    {}, {"name": "x"}, {"name": "x", "all_of": []}, {"name": "x", "all_of": [{"kind": "a"}], "window_bars": 0},
    {"name": "x", "all_of": [{"kind": "a"}], "window_bars": 101}, {"name": "x", "all_of": [{"kind": "a", "evil": 1}]},
    {"name": "x", "all_of": [{"kind": "a", "min_confidence": 2}]}, {"name": "x", "all_of": [{"kind": "a"}], "extra": 1},
    {"name": "x", "all_of": [{"kind": "a"}], "teaching_note": "you should buy here"},
    {"name": "x", "all_of": [{"kind": "a"}], "description": "price will rise"}, [], "string",
])
def test_invalid_specs_rejected(bad):
    with pytest.raises(SpecError):
        parse_rule(bad)


def test_examples_are_valid_and_policy_clean():
    for spec in EXAMPLE_RULES:
        parse_rule(spec)


def test_endpoint_validates_and_runs():
    c = TestClient(create_app(api_key="", rate_per_min=0))
    q = "iid=SYN:TEST&tick=0.5&start=2026-01-05T04:00:00Z&end=2026-01-05T06:00:00Z&tf=5m"
    ok = c.post(f"/api/v1/scenarios?{q}", json={"name": "any exhaustion", "all_of": [{"kind": "exhaustion_*"}], "window_bars": 2})
    assert ok.status_code == 200 and ok.json()["observations_considered"] > 0
    for m in ok.json()["matches"]:
        assert m["limitations"] and m["data_quality"]
    assert c.post(f"/api/v1/scenarios?{q}", json={"name": "x", "all_of": [{"kind": "a"}], "teaching_note": "buy now"}).status_code == 400
    assert c.get("/api/v1/scenarios/examples").json()["rules"]
