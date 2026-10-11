from datetime import timedelta

from ofx.domain import DataQuality as Q
from ofx.language import lint
from ofx.orderflow import detectors as d
from ofx.orderflow.footprint import Cell, FootprintBar, apply_session_cvd
from tests.conftest import T0


def bar(i, o, h, l, c, ask, bid, rows=None, q=Q.EXACT):
    """Bar with volume spread evenly over its rows unless rows given: {row: (bid, ask)}."""
    b = FootprintBar(T0 + timedelta(minutes=5 * i), T0 + timedelta(minutes=5 * i + 5), 1.0, o, h, l, c, quality=q)
    if rows is None:
        n = int(h - l) + 1
        rows = {int(l) + k: (bid / n, ask / n) for k in range(n)}
    b.rows = {r: Cell(bid_vol=bv, ask_vol=av) for r, (bv, av) in rows.items()}
    return b


def finish(bars):
    return apply_session_cvd(bars, lambda ts: 0)


def test_pivots_confirmed_only():
    s = [1, 3, 2, 1, 2, 1]
    assert d.pivots(s, 1, 1, "high") == [1, 4]
    assert d.pivots(s, 1, 2, "high") == [1]  # index 4 lacks 2 bars to its right: not yet confirmed


def test_delta_divergence_high_and_language():
    px = [10, 12, 11, 10, 13, 11, 10, 9]
    deltas = [5, 40, -20, -30, 5, -20, -25, -10]
    bars = finish([bar(i, p, p + 1, p - 1, p, 50 + x, 50 - x) if False else bar(i, p, p + 1, p - 1, p, max(x, 0) + 20, max(-x, 0) + 20) for i, (p, x) in enumerate(zip(px, deltas))])
    obs = d.delta_divergence(bars, 1, 1, z_min=0.5)
    assert any(o.kind == "delta_divergence_high" for o in obs)
    for o in obs:
        assert lint(o.summary) == [] and o.confidence <= 1.0 and o.alternatives


def test_estimated_quality_caps_confidence():
    px = [10, 12, 11, 10, 13, 11, 10, 9]
    deltas = [5, 40, -20, -30, 5, -20, -25, -10]
    bars = finish([bar(i, p, p + 1, p - 1, p, max(x, 0) + 20, max(-x, 0) + 20, q=Q.ESTIMATED) for i, (p, x) in enumerate(zip(px, deltas))])
    assert all(o.confidence <= 0.6 for o in d.delta_divergence(bars, 1, 1, z_min=0.5))


def test_absorption_fires_on_heavy_flow_no_progress():
    quiet = [bar(i, 10, 11, 10, 10.5, 10, 10) for i in range(6)]
    heavy = bar(6, 10, 14, 10, 10.2, 100, 20)  # large volume, positive delta, tiny body
    obs = d.absorption(finish(quiet + [heavy]), lookback=5)
    assert len(obs) == 1 and obs[0].kind == "absorption_ask_flow" and lint(obs[0].summary) == []


def test_absorption_ignores_efficient_move():
    quiet = [bar(i, 10, 11, 10, 10.5, 10, 10) for i in range(6)]
    trend = bar(6, 10, 14, 10, 14, 100, 20)  # same flow but price progressed
    assert d.absorption(finish(quiet + [trend]), lookback=5) == []


def test_exhaustion_top_two_flags():
    base = [bar(i, 10, 12, 10, 11, 30, 10) for i in range(5)]
    rows = {10: (50, 80), 11: (50, 60), 12: (10, 0)}  # zero ask at the top row, thin extreme
    top = bar(5, 11, 12.5, 10, 11, 0, 0, rows=rows)
    top.high_px = 13
    top.rows[13] = Cell(bid_vol=2, ask_vol=0)
    obs = d.exhaustion(finish(base + [top]), lookback=5)
    assert obs and obs[0].kind == "exhaustion_top" and "finished_print" in obs[0].evidence["flags"]


def test_liquidity_sweep_and_acceptance():
    def mk(seq):
        return finish([bar(i, p, h, l, c, 20, 20) for i, (p, h, l, c) in enumerate(seq)])
    base = [(10, 11, 9, 10), (10, 12, 10, 11), (11, 15, 11, 14), (14, 14, 11, 12), (12, 13, 10, 11), (11, 12, 10, 11)]
    sweep = mk(base + [(11, 17, 11, 13), (13, 14, 12, 12), (12, 13, 11, 12)])
    o = d.liquidity_sweep(sweep, 1.0, left=1, right=1, reclaim_bars=3)
    assert any(x.kind == "liquidity_sweep_high" for x in o)
    accept = mk(base + [(11, 17, 11, 17), (17, 18, 16, 17), (17, 18, 16, 17)])
    assert any(x.kind == "acceptance_beyond_high" for x in d.liquidity_sweep(accept, 1.0, left=1, right=1, reclaim_bars=3))


def test_imbalance_cluster_status():
    rows = {100: (5, 5), 101: (5, 40), 102: (5, 40), 103: (5, 40), 104: (5, 40)}
    z = bar(0, 100, 104, 100, 104, 0, 0, rows=rows)
    later = bar(1, 104, 105, 102, 103, 10, 10)
    obs = d.imbalance_clusters(finish([z, later]))
    assert obs and obs[0].kind == "imbalance_cluster_ask" and obs[0].evidence["status"] == "retested"


def test_cvd_trend_classes():
    up = finish([bar(i, 10 + i, 11 + i, 10 + i, 10.5 + i, 40, 10) for i in range(20)])
    assert d.cvd_trend(up).evidence["class"] == "aligned"
    flow_only = finish([bar(i, 10, 11, 10, 10.5, 40, 10) for i in range(20)])
    assert d.cvd_trend(flow_only).evidence["class"] == "flow_without_progress"
    assert d.cvd_trend(up[:5]) is None
