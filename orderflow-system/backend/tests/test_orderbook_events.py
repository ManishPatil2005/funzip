from datetime import timedelta

from ofx.domain import AggressorSide as S
from ofx.domain import DataQuality as Q
from ofx.domain import DepthLevel, DepthSnapshot
from ofx.language import lint
from ofx.orderflow.orderbook import IcebergTracker, OrderBook, WallTracker, spoof_like_pattern
from tests.conftest import T0, tr


def book(bids, asks):
    b = OrderBook(1.0)
    b.apply_snapshot(DepthSnapshot(T0, tuple(DepthLevel(p, q) for p, q in bids), tuple(DepthLevel(p, q) for p, q in asks)))
    return b


def base_bids(wall_qty=200, wall_px=95):
    return [(100 - i, wall_qty if 100 - i == wall_px else 10) for i in range(8)]


ASKS = [(101 + i, 10) for i in range(8)]


def test_wall_pulled_when_removed_untraded_as_price_approaches():
    wt = WallTracker(1.0, levels=8, k=3.0)
    assert wt.on_book(T0, book(base_bids(), ASKS)) == []  # wall at 95 appears, 5 ticks from touch
    # Wall removed and the bid now sits closer: touch at 97 -> distance of removed row 95 from best is 2
    ev = wt.on_book(T0 + timedelta(seconds=3), book([(97 - i, 10) for i in range(8)], [(98 + i, 10) for i in range(8)]))
    assert len(ev) == 1 and ev[0].outcome == "pulled" and ev[0].approached and ev[0].lifetime_s == 3


def test_wall_consumed_when_traded_through():
    wt = WallTracker(1.0, levels=8, k=3.0)
    wt.on_book(T0, book(base_bids(), ASKS))
    wt.on_trades([tr(1, 95, 190, S.BID, 1)])
    ev = wt.on_book(T0 + timedelta(seconds=2), book([(94 - i, 10) for i in range(8)], ASKS))
    assert ev and ev[0].outcome == "consumed" and ev[0].executed_share > 0.9


def test_spoof_like_requires_repeats_and_is_language_clean():
    wt = WallTracker(1.0, levels=8, k=3.0)
    events = []
    for n in range(3):
        t = T0 + timedelta(seconds=10 * n)
        wt.on_book(t, book(base_bids(), ASKS))
        events += wt.on_book(t + timedelta(seconds=2), book([(97 - i, 10) for i in range(8)], [(98 + i, 10) for i in range(8)]))
    assert len(events) == 3
    obs = spoof_like_pattern(events)
    assert len(obs) == 1 and obs[0].confidence <= 0.6 and lint(obs[0].summary) == []
    assert spoof_like_pattern(events[:2]) == []


def test_iceberg_like_after_refills():
    it = IcebergTracker(1.0, multiple=3.0, min_refills=3)
    b = book([(99, 10)], [(100, 20), (101, 10)])
    found = []
    for n in range(4):
        it.on_trade(T0 + timedelta(seconds=n), tr(n, 100, 20, S.ASK, n), b)  # executes the full displayed size
        found += it.on_book(T0 + timedelta(seconds=n, milliseconds=500), b)  # level is displayed again at full size
    assert len(found) == 1 and found[0].kind == "iceberg_like_level" and found[0].data_quality is Q.ESTIMATED
    assert lint(found[0].summary) == [] and found[0].confidence <= 0.6
