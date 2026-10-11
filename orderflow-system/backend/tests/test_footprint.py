from datetime import UTC, timedelta

import pytest

from ofx.domain import AggressorSide as S
from ofx.domain import DataQuality as Q
from ofx.domain import Quote
from ofx.orderflow.classify import Method, classify_trades, split_bar_volume
from ofx.orderflow.footprint import ImbalanceConfig, apply_session_cvd, build_footprint, find_imbalances, stacked_imbalances
from tests.conftest import T0, tr

M1 = timedelta(minutes=1)


def test_cells_delta_and_unknown_kept_apart():
    bars = build_footprint([tr(1, 100, 5, S.ASK), tr(2, 100, 3, S.BID), tr(3, 100, 2, S.UNKNOWN, method="none")], 1.0, M1)
    (b,) = bars
    c = b.rows[100]
    assert (c.ask_vol, c.bid_vol, c.unknown_vol) == (5, 3, 2)
    assert b.delta == 2 and b.volume == 10 and b.unknown_share == pytest.approx(0.2)
    assert b.quality is Q.ESTIMATED


def test_exact_quality_when_all_exchange():
    (b,) = build_footprint([tr(1, 100, 1)], 1.0, M1)
    assert b.quality is Q.EXACT


def test_bar_boundaries_and_offset():
    bars = build_footprint([tr(59, 100, 1), tr(60, 100, 1)], 1.0, M1)
    assert len(bars) == 2
    shifted = build_footprint([tr(59, 100, 1), tr(60, 100, 1)], 1.0, M1, align_offset=timedelta(seconds=30))
    assert len(shifted) == 1  # boundary moved to :30 so both prints share a bar


def test_cvd_resets_per_session():
    from datetime import datetime

    from ofx.domain import Trade
    a = tr(1, 100, 4, S.ASK)
    b = Trade(datetime(2026, 1, 6, 4, 0, 1, tzinfo=UTC), 100, 6, S.ASK, 2, "exchange")
    bars = apply_session_cvd(build_footprint([a, b], 1.0, M1))
    assert bars[0].cvd_close == 4 and bars[1].cvd_open == 0 and bars[1].cvd_close == 6


def test_diagonal_imbalance_and_stack():
    # asks at rows 101..104 each 30, bids one row below only 5 -> ask imbalance at 101..104 (ratio 3)
    trades, s = [], 0
    for r in range(100, 105):
        s += 1
        trades.append(tr(s, r, 5, S.BID, s))
    for r in range(101, 105):
        s += 1
        trades.append(tr(s, r, 30, S.ASK, s))
    (b,) = build_footprint(trades, 1.0, M1)
    imb = [i for i in find_imbalances(b) if i.side == "ask"]
    assert [i.row for i in imb] == [101, 102, 103, 104]
    st = stacked_imbalances(imb, 3)
    assert len(st) == 1 and st[0].n_rows == 4


def test_imbalance_edge_row_not_flagged_and_min_volume():
    (b,) = build_footprint([tr(1, 100, 9, S.ASK, 1), tr(2, 101, 1, S.BID, 2)], 1.0, M1)
    assert find_imbalances(b) == []  # row 100 has no row below inside the bar
    (b2,) = build_footprint([tr(1, 100, 1, S.BID, 1), tr(2, 101, 2, S.ASK, 2)], 1.0, M1)
    assert find_imbalances(b2, ImbalanceConfig(ratio=3, min_volume=5)) == []
    assert len(find_imbalances(b2, ImbalanceConfig(ratio=2))) == 1


def test_classification_methods():
    trades = [tr(1, 100.5, 1, S.UNKNOWN, 1, "none"), tr(2, 99.5, 1, S.UNKNOWN, 2, "none"), tr(3, 99.5, 1, S.UNKNOWN, 3, "none")]
    out = classify_trades(trades, [], Method.TICK)
    assert [t.side for t in out][1:] == [S.BID, S.BID]  # down tick, then zero tick inherits
    quotes = [Quote(T0, 99.5, 100.5)]
    q = classify_trades([tr(1, 100.5, 1, S.UNKNOWN, 1, "none"), tr(2, 99.5, 1, S.UNKNOWN, 2, "none"), tr(3, 100.0, 1, S.UNKNOWN, 3, "none")],
                        quotes, Method.QUOTE)
    assert q[0].side is S.ASK and q[1].side is S.BID and q[2].side is S.UNKNOWN  # midpoint never guessed


def test_split_bar_volume_conserves_total():
    a, b = split_bar_volume(100, 10, 12, 9, 11.5)
    assert a + b == pytest.approx(100) and a > b
