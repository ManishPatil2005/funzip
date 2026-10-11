import pytest

from ofx.domain import DataQuality as Q
from ofx.domain import Trade, price_to_row, weakest
from ofx.language import LanguagePolicyError, lint, require_compliant
from ofx.orderflow.common import local_extrema, poc_index, prominence, value_area_indices
from ofx.orderflow.observation import Observation, cap_confidence
from tests.conftest import T0, tr


def test_price_rows_round_not_floor():
    assert price_to_row(100.3, 0.1) == 1003  # naive floor(100.3/0.1) gives 1002
    assert price_to_row(0.3, 0.1) == 3


def test_weakest_quality():
    assert weakest(Q.EXACT, Q.ESTIMATED) is Q.ESTIMATED


def test_trade_validation():
    from datetime import datetime
    with pytest.raises(ValueError):
        Trade(datetime(2026, 1, 1), 1, 1)
    with pytest.raises(ValueError):
        tr(0, 0, 1)


def test_language_lint():
    assert lint("price accepted above the level") == []
    assert lint("You should BUY here") != []
    with pytest.raises(LanguagePolicyError):
        require_compliant("set a stop-loss")
    with pytest.raises(LanguagePolicyError):
        Observation("x", T0, T0, "this will go up", Q.EXACT, "m", 0.5)


def test_confidence_cap():
    assert cap_confidence(0.9, Q.ESTIMATED) == 0.6
    assert cap_confidence(0.9, Q.BAR_APPROXIMATED) == 0.35
    assert cap_confidence(0.9, Q.EXACT) == 0.9


def test_poc_ties_prefer_centre():
    assert poc_index([5, 1, 1, 1, 5, 1, 1]) == 4  # centre index 3: |4-3| < |0-3|


def test_value_area_dalton_two_rows():
    vals = [1, 2, 3, 10, 4, 3, 2, 1]  # total 26; 70% = 18.2
    lo, hi = value_area_indices(vals, 3)
    assert lo <= 3 <= hi and sum(vals[lo:hi + 1]) >= 0.7 * sum(vals)


def test_extrema_plateau_and_prominence():
    assert local_extrema([1, 3, 3, 1], "max") == [1]
    assert prominence([0, 5, 1, 3, 0], 3, "max") == 2
