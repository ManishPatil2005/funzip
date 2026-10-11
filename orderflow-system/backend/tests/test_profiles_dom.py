from datetime import UTC, datetime, timedelta, timezone

import numpy as np
import pytest

from ofx.domain import AggressorSide as S
from ofx.domain import Candle, DepthLevel, DepthSnapshot
from ofx.orderflow import heatmap as hm
from ofx.orderflow import market_profile as mp
from ofx.orderflow import volume_profile as vp
from ofx.orderflow.orderbook import OrderBook, book_imbalance, find_walls
from tests.conftest import T0, tr


def test_volume_profile_poc_va_nodes():
    trades = []
    seq = 0
    shape = {100: 2, 101: 5, 102: 20, 103: 6, 104: 3, 105: 6, 106: 22, 107: 5, 108: 2}
    for px, q in shape.items():
        seq += 1
        trades.append(tr(seq, px, q, S.ASK, seq))
    prof = vp.from_trades(trades, 1.0)
    k = vp.key_levels(prof)
    assert k.poc == 106 and k.val <= k.poc <= k.vah and k.value_area_volume_share >= 0.7
    kinds = [(n.kind, n.price) for n in vp.nodes(prof, smooth=1, prominence_share=0.1)]
    assert ("HVN", 102) in kinds and ("HVN", 106) in kinds and ("LVN", 104) in kinds


def test_candle_profile_is_flagged_and_conserves_volume():
    c = [Candle(T0, 10, 12, 9, 11, 300.0)]
    p = vp.from_candles(c, 1.0)
    assert p.approximated and p.total == pytest.approx(300.0)
    assert vp.merge([p, p]).total == pytest.approx(600.0)


def test_tpo_levels_ib_and_single_prints():
    ist = timezone(timedelta(hours=5, minutes=30))
    day = datetime(2026, 1, 5, 9, 15, tzinfo=ist)
    spans = [(100, 104), (101, 105), (102, 106), (102, 104), (103, 111), (110, 112)]
    candles = [Candle(day + timedelta(minutes=30 * i), lo, hi, lo, hi, 10) for i, (lo, hi) in enumerate(spans)]
    (p,) = mp.build_tpo(candles, mp.NSE_EQUITY, 1.0, 30)
    lv = mp.tpo_levels(p)
    assert (lv.ib_low, lv.ib_high) == (100, 105)
    assert lv.high == 112 and lv.low == 100 and lv.val <= lv.poc <= lv.vah
    assert any(a <= 108 <= b for a, b in lv.single_print_ranges) or lv.top_tail_rows >= 1


def test_session_outside_hours_ignored():
    assert mp.NSE_EQUITY.session_start(datetime(2026, 1, 5, 20, 0, tzinfo=UTC)) is None


def test_composite_rejects_mixed_ticks():
    a = mp.TPOProfile(T0, 1.0, 30, {1: 1}, {})
    b = mp.TPOProfile(T0, 0.5, 30, {1: 1}, {})
    with pytest.raises(ValueError):
        mp.composite([a, b], "weekly")


def _snap(bids, asks, sec=0):
    return DepthSnapshot(T0 + timedelta(seconds=sec), tuple(DepthLevel(p, q) for p, q in bids), tuple(DepthLevel(p, q) for p, q in asks))


def test_book_imbalance_and_walls():
    book = OrderBook(1.0)
    book.apply_snapshot(_snap([(99, 100), (98, 10), (97, 10), (96, 10)], [(100, 10), (101, 10), (102, 10), (103, 10)]))
    assert book_imbalance(book, 4, "flat") == pytest.approx((130 - 40) / 170)
    walls = find_walls(book, "bid", levels=4, k=3.0)
    assert [w.price for w in walls] == [99]


def test_heatmap_max_vs_avg_and_intensity():
    snaps = [_snap([(99, 10)], [(100, 50)], 0), _snap([(99, 10)], [(100, 0.0001)], 5)]
    t1 = T0 + timedelta(seconds=10)
    h = hm.build_heatmap(snaps, 1.0, T0, t1, 10.0, 99, 100, "max")
    assert h.matrix[1, 0] == 50
    h2 = hm.build_heatmap(snaps, 1.0, T0, t1, 10.0, 99, 100, "avg")
    assert h2.matrix[1, 0] == pytest.approx(25.00005, rel=1e-3)
    m = np.array([[1.0, 10.0, 1000.0, 0.0]])
    for scale in ("linear", "log", "percentile"):
        x = hm.intensity(m, scale)
        assert x.min() >= 0 and x.max() <= 1 and x[0, 3] == 0
    assert hm.color_at(0.0) == hm.COLOR_STOPS[0][1] and hm.color_at(1.0) == hm.COLOR_STOPS[-1][1]
