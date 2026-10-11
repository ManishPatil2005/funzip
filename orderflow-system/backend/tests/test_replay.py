from datetime import UTC, datetime, timedelta

from ofx.language import lint
from ofx.providers.synthetic import generate_trades
from ofx.replay import replay_by_day, run_detectors


def test_replay_groups_by_day_and_summarises():
    d1 = generate_trades(datetime(2026, 1, 5, 4, 0, tzinfo=UTC), 1800, seed=1)
    d2 = generate_trades(datetime(2026, 1, 6, 4, 0, tzinfo=UTC), 1800, seed=2)
    res = replay_by_day(d1 + d2, 0.5, timedelta(minutes=1))
    assert list(res) == ["2026-01-05", "2026-01-06"]
    for day in res.values():
        assert day["bars"] > 20 and day["trades"] > 1000
        assert sum(day["by_kind"].values()) == day["observations"]
        assert day["mean_confidence"] is None or 0 <= day["mean_confidence"] <= 1


def test_replay_is_deterministic_and_language_clean():
    t = generate_trades(datetime(2026, 1, 5, 4, 0, tzinfo=UTC), 1800, seed=3)
    _, a = run_detectors(t, 0.5, timedelta(minutes=1))
    _, b = run_detectors(t, 0.5, timedelta(minutes=1))
    assert [o.to_dict() for o in a] == [o.to_dict() for o in b] and a
    assert all(lint(o.summary) == [] for o in a)


def test_no_lookahead_prefix_stability():
    """Observations ending inside the first half must not change when later data is appended (no repaint)."""
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    full = generate_trades(start, 1800, seed=5)
    cut = start + timedelta(minutes=15)
    part = [t for t in full if t.ts < cut]
    _, o_part = run_detectors(part, 0.5, timedelta(minutes=1))
    _, o_full = run_detectors(full, 0.5, timedelta(minutes=1))
    early = lambda obs: sorted((o.kind, o.ts_start, o.ts_end, o.summary) for o in obs if o.ts_end < cut - timedelta(minutes=5))  # noqa: E731
    assert early(o_part) == early(o_full)
