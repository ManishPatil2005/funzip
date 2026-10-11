"""Shared building blocks: POC, value area, extrema with prominence."""
from __future__ import annotations

from collections.abc import Sequence


def poc_index(values: Sequence[float]) -> int:
    """Index of the maximum; ties resolve to the one closest to the centre.

    Rationale: with equal maxima, the centre is the least biased choice and is
    the convention used by most Market Profile tools.
    """
    if not values:
        raise ValueError("empty profile")
    peak = max(values)
    mid = (len(values) - 1) / 2
    return min((i for i, v in enumerate(values) if v == peak), key=lambda i: (abs(i - mid), i))


def value_area_indices(values: Sequence[float], poc_i: int, pct: float = 0.70) -> tuple[int, int]:
    """Inclusive (low_index, high_index) covering `pct` of the total.

    Dalton's method: from the POC, compare the next two rows above with the
    next two rows below and absorb the heavier pair; ties go upward.
    """
    n, total = len(values), float(sum(values))
    if n == 0 or total <= 0:
        raise ValueError("empty or zero-volume profile")
    lo = hi = poc_i
    acc = float(values[poc_i])
    while acc < pct * total:
        can_up, can_dn = hi + 1 < n, lo - 1 >= 0
        if not can_up and not can_dn:
            break
        up = (values[hi + 1] if can_up else 0.0) + (values[hi + 2] if hi + 2 < n else 0.0)
        dn = (values[lo - 1] if can_dn else 0.0) + (values[lo - 2] if lo - 2 >= 0 else 0.0)
        if can_up and (up >= dn or not can_dn):
            new_hi = min(hi + 2, n - 1)
            acc += sum(values[hi + 1:new_hi + 1])
            hi = new_hi
        else:
            new_lo = max(lo - 2, 0)
            acc += sum(values[new_lo:lo])
            lo = new_lo
    return lo, hi


def local_extrema(values: Sequence[float], kind: str) -> list[int]:
    """Indices of local maxima ('max') or minima ('min'); plateaus yield their midpoint.

    Boundaries count as lower than any value for maxima (and higher for minima), so
    an edge sample can be an extremum when it beats its only neighbour.
    """
    sign = 1.0 if kind == "max" else -1.0
    v = [sign * x for x in values]
    n, out, i = len(v), [], 0
    while i < n:
        j = i
        while j + 1 < n and v[j + 1] == v[i]:
            j += 1
        left_ok = i == 0 or v[i - 1] < v[i]
        right_ok = j == n - 1 or v[j + 1] < v[i]
        if left_ok and right_ok:
            out.append((i + j) // 2)
        i = j + 1
    return out


def prominence(values: Sequence[float], idx: int, kind: str) -> float:
    """Topographic prominence of the extremum at idx (for 'min', depth of the valley)."""
    sign = 1.0 if kind == "max" else -1.0
    v = [sign * x for x in values]
    peak = v[idx]
    left_min = peak
    for k in range(idx - 1, -1, -1):
        if v[k] > peak:
            break
        left_min = min(left_min, v[k])
    right_min = peak
    for k in range(idx + 1, len(v)):
        if v[k] > peak:
            break
        right_min = min(right_min, v[k])
    return peak - max(left_min, right_min)


def moving_average(values: Sequence[float], window: int) -> list[float]:
    """Centred moving average, window shrinks at the edges. window must be odd or 1."""
    if window <= 1:
        return [float(x) for x in values]
    half = window // 2
    n = len(values)
    out = []
    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        out.append(sum(values[lo:hi]) / (hi - lo))
    return out
