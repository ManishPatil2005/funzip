import pandas as pd
import pytest

from app.data.universe import Instrument
from app.profile import market_profile as mp

INST = Instrument("TEST", "TEST.NS", "TEST", "NSE", "equity", 1.0)


def session(day, bars):
    """bars: list of (open, high, low, close) for consecutive 30-minute periods from 09:15 IST."""
    idx = pd.date_range(f"{day} 09:15", periods=len(bars), freq="30min", tz="Asia/Kolkata")
    df = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 1000.0
    return df


def test_nice_tick_scales_with_range_and_respects_base_tick():
    assert mp.nice_tick(2.5, 0.05) == pytest.approx(0.05)
    assert mp.nice_tick(25, 0.05) == pytest.approx(0.5)
    assert mp.nice_tick(500, 1.0) == pytest.approx(10.0)
    assert mp.nice_tick(0.0, 0.05) == pytest.approx(0.05)


def test_value_area_expands_toward_heavier_side_and_covers_70pct():
    counts = [1, 2, 3, 6, 9, 7, 4, 2, 1]
    poc = counts.index(9)
    lo, hi = mp.value_area(counts, poc)
    covered = sum(counts[lo:hi + 1]) / sum(counts)
    assert covered >= 0.70
    assert lo <= poc <= hi
    # below pair (6+3=9) beats above pair (7+4=11)? above wins first, then below
    assert hi >= poc + 1


def test_poc_and_value_area_on_symmetric_profile():
    bars = [(100, 104, 96, 100)] * 4 + [(100, 102, 98, 100)] * 4 + [(100, 101, 99, 100)] * 5
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=1.0)
    assert rep["poc"] == 99.0 or rep["poc"] == 100.0
    assert rep["val"] <= rep["poc"] < rep["vah"]
    assert rep["total_tpo"] == sum(r["count"] for r in rep["rows"])
    assert rep["high"] == 104 and rep["low"] == 96
    # each period contributes at most one letter per row
    assert all(len(set(r["letters"])) == len(r["letters"]) for r in rep["rows"])


def test_letters_and_expected_period_count_for_nse():
    rep = mp.analyse_session(session("2026-10-05", [(100, 101, 99, 100)] * 13), INST, tick=1.0)
    assert [p["letter"] for p in rep["periods"]][:3] == ["A", "B", "C"]
    assert rep["periods_expected"] == 13 and rep["complete"]


def test_initial_balance_is_first_hour():
    bars = [(100, 102, 99, 101), (101, 103, 100, 102)] + [(102, 110, 101, 109)] * 6
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=1.0)
    assert rep["ib"]["high"] == 103 and rep["ib"]["low"] == 99
    assert rep["ib"]["ext_up"] == 7 and rep["ib"]["ext_down"] == 0


def test_trend_day_classification():
    bars = [(100, 101, 99.5, 100.5), (100.5, 101.5, 100, 101)] + [
        (101 + i * 2, 103 + i * 2, 101 + i * 2, 103 + i * 2) for i in range(10)]
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=0.5)
    assert rep["day_type"] == "Trend Day"
    assert rep["shape"].startswith("Elongated")


def test_neutral_day_extends_both_sides_of_ib():
    bars = [(100, 102, 98, 100), (100, 102, 98, 100), (100, 106, 99, 104), (104, 105, 94, 96),
            (96, 101, 95, 100), (100, 102, 98, 100)]
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=1.0)
    assert rep["day_type"] in ("Neutral", "Neutral Extreme")


def test_normal_day_has_no_extension():
    bars = [(100, 110, 90, 100), (100, 108, 92, 101)] + [(100, 105, 95, 100)] * 5
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=1.0)
    assert rep["day_type"] == "Normal"


def test_double_distribution_detected_with_single_print_gap():
    bars = [(100, 101, 99, 100)] * 5 + [(100, 104, 100, 104)]
    bars += [(104, 111, 109, 110), (110, 112, 108, 111), (111, 112, 109, 110), (110, 112, 109, 111),
             (111, 112, 109, 111), (111, 112, 109, 110)]
    rep = mp.analyse_session(session("2026-10-05", bars), INST, tick=1.0)
    assert rep["day_type"] == "Double Distribution"
    assert rep["shape"].startswith("B")
    assert rep["single_prints"]


def test_excess_tail_vs_poor_high():
    # single-print tail above a heavy body => excess at high
    body = [(100, 105, 100, 102)] * 6 + [(102, 108, 105, 106)]
    rep = mp.analyse_session(session("2026-10-05", body), INST, tick=1.0)
    assert rep["high_structure"] == "excess"
    # many periods touching the same high => poor high
    flat = [(100, 105, 99, 102)] * 6
    rep = mp.analyse_session(session("2026-10-05", flat), INST, tick=1.0)
    assert rep["high_structure"] == "poor" and rep["low_structure"] == "poor"


def test_open_drive_and_rejection():
    drive_up = [(100, 106, 100, 106), (106, 109, 105, 108)] + [(108, 110, 107, 109)] * 4
    rep = mp.analyse_session(session("2026-10-05", drive_up), INST, tick=1.0)
    assert rep["open_type"] == {"type": "Open-Drive", "direction": "up"}
    reject = [(100, 108, 99.5, 101), (101, 102, 92, 93)] + [(93, 95, 92, 94)] * 4
    rep = mp.analyse_session(session("2026-10-05", reject), INST, tick=1.0)
    assert rep["open_type"] == {"type": "Open-Rejection-Reverse", "direction": "down"}
    auction = [(100, 102, 98, 100), (100, 101, 99, 100)] + [(100, 102, 98, 100)] * 4
    assert mp.analyse_session(session("2026-10-05", auction), INST, tick=1.0)["open_type"]["type"] == "Open-Auction (in range)"


def prior_summary(**kw):
    base = {"val": 100, "vah": 110, "poc": 105, "high": 115, "low": 95}
    base.update(kw)
    return base


def today_summary(val, vah):
    return {"val": val, "vah": vah}


def test_value_relationship_all_cases():
    p = prior_summary()
    assert mp.value_relationship(today_summary(111, 120), p) == "higher"
    assert mp.value_relationship(today_summary(80, 99), p) == "lower"
    assert mp.value_relationship(today_summary(102, 108), p) == "inside"
    assert mp.value_relationship(today_summary(95, 115), p) == "outside"
    assert mp.value_relationship(today_summary(105, 115), p) == "overlapping higher"
    assert mp.value_relationship(today_summary(95, 105), p) == "overlapping lower"


def test_open_location_buckets():
    p = prior_summary()
    assert [mp.open_location(x, p) for x in (120, 112, 105, 97, 90)] == [
        "above prior range", "above prior value", "inside prior value", "below prior value", "below prior range"]


def test_eighty_percent_rule_triggers_after_two_closes_inside_value():
    p = prior_summary()
    periods = [{"letter": "A", "close": 112}, {"letter": "B", "close": 108}, {"letter": "C", "close": 107}]
    res = mp.eighty_percent_rule({"open": 113, "periods": periods}, p)
    assert res["applicable"] and res["triggered"] and res["direction"] == "down" and res["target"] == 100
    periods = [{"letter": "A", "close": 112}, {"letter": "B", "close": 108}, {"letter": "C", "close": 113}]
    assert not mp.eighty_percent_rule({"open": 113, "periods": periods}, p)["triggered"]
    assert not mp.eighty_percent_rule({"open": 105, "periods": periods}, p)["applicable"]


def test_naked_poc_detection():
    a = [{"date": "d1", "poc": 100, "low": 95, "high": 105}, {"date": "d2", "poc": 120, "low": 112, "high": 125},
         {"date": "d3", "poc": 130, "low": 126, "high": 135}]
    assert mp.naked_pocs(a) == [{"date": "d1", "price": 100}, {"date": "d2", "price": 120}]
    a[2]["low"] = 99
    assert mp.naked_pocs(a) == [{"date": "d2", "price": 120}] or mp.naked_pocs(a) == []


def test_build_report_end_to_end_and_bias_levels_are_coherent():
    from app.data.provider import SyntheticProvider
    from app.data.universe import INSTRUMENTS

    for sym in ("RELIANCE", "NIFTY50", "GOLD", "SILVER"):
        inst = INSTRUMENTS[sym]
        rep = mp.build_report(SyntheticProvider().history(inst, "30m", "1mo"), inst)
        b = rep["bias"]
        assert b["signal"] in ("BUY", "SELL", "NEUTRAL")
        assert (b["signal"] == "NEUTRAL") == (b["levels"] is None)
        assert abs(b["score"]) < 3 if b["signal"] == "NEUTRAL" else abs(b["score"]) >= 3
        lv = b["levels"]
        if lv and b["signal"] == "BUY":
            assert lv["stop"] < lv["entry"] < lv["target1"] <= lv["target2"]
        if lv and b["signal"] == "SELL":
            assert lv["stop"] > lv["entry"] > lv["target1"] >= lv["target2"]
        assert rep["profile"]["val"] <= rep["profile"]["poc"] <= rep["profile"]["vah"]


def test_report_rejects_daily_data_and_unknown_date():
    from app.data.provider import SyntheticProvider
    from app.data.universe import INSTRUMENTS

    inst = INSTRUMENTS["TCS"]
    with pytest.raises(mp.ProfileError):
        mp.build_report(SyntheticProvider().history(inst, "1d", "1y"), inst)
    with pytest.raises(mp.ProfileError):
        mp.build_report(SyntheticProvider().history(inst, "30m", "1mo"), inst, date="1999-01-01")


def test_ascii_render_marks_poc():
    rep = mp.analyse_session(session("2026-10-05", [(100, 104, 98, 102)] * 6), INST, tick=1.0)
    text = mp.render_ascii(rep)
    assert "POC" in text and "A" in text
