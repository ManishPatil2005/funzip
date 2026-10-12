"""TPO (Market Profile): session, daily, weekly and composite profiles."""
from __future__ import annotations

import string
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ofx.domain import Candle, price_to_row, row_to_price
from ofx.orderflow.common import poc_index, value_area_indices

LETTERS = string.ascii_uppercase + string.ascii_lowercase


@dataclass(frozen=True)
class SessionSpec:
    """A trading session: opens at `open_time` (local to `tz`) and lasts `duration`."""

    name: str
    tz: str
    open_time: time
    duration: timedelta

    def session_start(self, ts: datetime) -> datetime | None:
        """UTC start of the session containing ts, or None if ts is outside any session."""
        zone = ZoneInfo(self.tz)
        local = ts.astimezone(zone)
        start = datetime.combine(local.date(), self.open_time, tzinfo=zone)
        if local < start:
            start -= timedelta(days=1)
        if local >= start + self.duration:
            return None
        return start.astimezone(UTC)


NSE_EQUITY = SessionSpec("NSE", "Asia/Kolkata", time(9, 15), timedelta(hours=6, minutes=15))
MCX_COMMODITY = SessionSpec("MCX", "Asia/Kolkata", time(9, 0), timedelta(hours=14, minutes=30))
CRYPTO_UTC_DAY = SessionSpec("CRYPTO", "UTC", time(0, 0), timedelta(hours=24))


@dataclass
class TPOProfile:
    start: datetime
    tick: float
    period_minutes: int
    counts: dict[int, int] = field(default_factory=dict)  # row -> TPO count
    letters: dict[int, str] | None = field(default_factory=dict)  # None for composites
    open_px: float | None = None
    close_px: float | None = None
    ib_high_row: int | None = None
    ib_low_row: int | None = None
    n_periods: int = 0
    sessions: int = 1
    scope: str = "session"

    def dense(self) -> tuple[int, list[int]]:
        lo, hi = min(self.counts), max(self.counts)
        return lo, [self.counts.get(r, 0) for r in range(lo, hi + 1)]

    @property
    def high_row(self) -> int:
        return max(self.counts)

    @property
    def low_row(self) -> int:
        return min(self.counts)


def build_tpo(candles: Iterable[Candle], spec: SessionSpec, tick: float, period_minutes: int = 30) -> list[TPOProfile]:
    """One profile per session. Candles must be no coarser than the TPO period."""
    if period_minutes < 1:
        raise ValueError("period_minutes must be >= 1")
    by_session: dict[datetime, list[Candle]] = {}
    for c in sorted(candles, key=lambda c: c.ts_open):
        s = spec.session_start(c.ts_open)
        if s is not None:
            by_session.setdefault(s, []).append(c)

    out: list[TPOProfile] = []
    for start in sorted(by_session):
        cs = by_session[start]
        periods: dict[int, list[Candle]] = {}
        for c in cs:
            idx = int((c.ts_open - start).total_seconds() // (period_minutes * 60))
            periods.setdefault(idx, []).append(c)
        letters: dict[int, str] = {}
        prof = TPOProfile(start, tick, period_minutes, letters=letters, scope="session")
        prof.open_px, prof.close_px = cs[0].open, cs[-1].close
        order = sorted(periods)
        for n, idx in enumerate(order):
            lo = min(price_to_row(c.low, tick) for c in periods[idx])
            hi = max(price_to_row(c.high, tick) for c in periods[idx])
            letter = LETTERS[idx % len(LETTERS)]
            for r in range(lo, hi + 1):
                prof.counts[r] = prof.counts.get(r, 0) + 1
                letters[r] = letters.get(r, "") + letter
            if n < 2:  # initial balance = first two periods
                prof.ib_low_row = lo if prof.ib_low_row is None else min(prof.ib_low_row, lo)
                prof.ib_high_row = hi if prof.ib_high_row is None else max(prof.ib_high_row, hi)
        prof.n_periods = len(order)
        out.append(prof)
    return out


def composite(profiles: Sequence[TPOProfile], scope: str) -> TPOProfile:
    """Merge sessions (daily from sessions, weekly from days). Letters are dropped."""
    if not profiles:
        raise ValueError("nothing to merge")
    first = profiles[0]
    out = TPOProfile(first.start, first.tick, first.period_minutes, letters=None, scope=scope)
    for p in profiles:
        if abs(p.tick - first.tick) > 1e-12:
            raise ValueError("cannot merge profiles with different tick sizes")
        for r, n in p.counts.items():
            out.counts[r] = out.counts.get(r, 0) + n
        out.n_periods += p.n_periods
    out.sessions = len(profiles)
    out.open_px, out.close_px = first.open_px, profiles[-1].close_px
    return out


def daily(profiles: Sequence[TPOProfile], tz: str) -> list[TPOProfile]:
    """Group sessions by local calendar date (single-session markets: identity)."""
    groups: dict[date, list[TPOProfile]] = {}
    for p in profiles:
        groups.setdefault(p.start.astimezone(ZoneInfo(tz)).date(), []).append(p)
    out = []
    for d in sorted(groups):
        g = groups[d]
        out.append(g[0] if len(g) == 1 else composite(g, "daily"))
    for p in out:
        p.scope = "daily"
    return out


def weekly(profiles: Sequence[TPOProfile], tz: str) -> list[TPOProfile]:
    """ISO-week composites of daily profiles."""
    groups: dict[tuple[int, int], list[TPOProfile]] = {}
    for p in profiles:
        iso = p.start.astimezone(ZoneInfo(tz)).isocalendar()
        groups.setdefault((iso[0], iso[1]), []).append(p)
    return [composite(groups[k], "weekly") for k in sorted(groups)]


@dataclass(frozen=True)
class TPOLevels:
    poc: float
    vah: float
    val: float
    ib_high: float | None
    ib_low: float | None
    high: float
    low: float
    single_print_ranges: tuple[tuple[float, float], ...]
    top_tail_rows: int
    bottom_tail_rows: int


def tpo_levels(p: TPOProfile, pct: float = 0.70) -> TPOLevels:
    """Key levels. Single prints are interior runs (>= 2 rows) of count == 1; tails are
    the single-count rows touching the high or low."""
    first, dense = p.dense()
    poc_i = poc_index(dense)
    lo_i, hi_i = value_area_indices(dense, poc_i, pct)
    n = len(dense)
    top = 0
    while top < n and dense[n - 1 - top] == 1:
        top += 1
    bottom = 0
    while bottom < n and dense[bottom] == 1:
        bottom += 1
    runs, start = [], None
    for i in range(bottom, n - top):
        if dense[i] == 1:
            start = i if start is None else start
        elif start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, n - top - 1))
    t = p.tick
    return TPOLevels(
        poc=row_to_price(first + poc_i, t), vah=row_to_price(first + hi_i, t), val=row_to_price(first + lo_i, t),
        ib_high=row_to_price(p.ib_high_row, t) if p.ib_high_row is not None else None,
        ib_low=row_to_price(p.ib_low_row, t) if p.ib_low_row is not None else None,
        high=row_to_price(first + n - 1, t), low=row_to_price(first, t),
        single_print_ranges=tuple((row_to_price(first + a, t), row_to_price(first + b, t)) for a, b in runs if b - a + 1 >= 2),
        top_tail_rows=top, bottom_tail_rows=bottom,
    )


def bar_align_offset(spec: SessionSpec, timeframe: timedelta, ref: datetime | None = None) -> timedelta:
    """Offset so time bars start exactly at the session open (e.g. NSE 30-minute bars at 09:15, 09:45 IST).

    Returned value is (open instant in UTC) modulo the timeframe, for use as `align_offset` in build_footprint.
    """
    zone = ZoneInfo(spec.tz)
    day = (ref or datetime(2026, 1, 5, tzinfo=UTC)).astimezone(zone).date()
    open_utc = datetime.combine(day, spec.open_time, tzinfo=zone).astimezone(UTC)
    secs = int(timeframe.total_seconds())
    return timedelta(seconds=int(open_utc.timestamp()) % secs)
