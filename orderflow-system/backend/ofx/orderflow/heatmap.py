"""Liquidity heatmap: depth snapshots to a time x price matrix, intensity scaling, color map."""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import numpy as np

from ofx.domain import DepthSnapshot, price_to_row


@dataclass
class Heatmap:
    t_start: datetime
    dt_seconds: float
    row_lo: int
    tick: float
    matrix: np.ndarray  # shape (rows, cols); quantity resting at row r during column c

    @property
    def shape(self) -> tuple[int, int]:
        return self.matrix.shape  # type: ignore[return-value]


def build_heatmap(
    snapshots: Sequence[DepthSnapshot], tick: float, t_start: datetime, t_end: datetime,
    dt_seconds: float, row_lo: int, row_hi: int, mode: Literal["max", "avg"] = "max",
) -> Heatmap:
    """Each snapshot is treated as valid until the next one (step function).

    mode 'max': the largest quantity seen at the row inside the time bucket (shows brief walls).
    mode 'avg': time-weighted mean quantity (shows persistent liquidity).
    """
    if dt_seconds <= 0 or row_hi < row_lo:
        raise ValueError("invalid heatmap geometry")
    total = (t_end - t_start).total_seconds()
    cols = max(1, int(np.ceil(total / dt_seconds)))
    rows = row_hi - row_lo + 1
    mat = np.zeros((rows, cols), dtype=np.float64)
    snaps = sorted(snapshots, key=lambda s: s.ts)

    for k, s in enumerate(snaps):
        start = (s.ts - t_start).total_seconds()
        end = (snaps[k + 1].ts - t_start).total_seconds() if k + 1 < len(snaps) else total
        if end <= 0 or start >= total:
            continue
        start, end = max(start, 0.0), min(end, total)
        c0, c1 = int(start // dt_seconds), min(cols - 1, int((end - 1e-9) // dt_seconds))
        levels = [(price_to_row(l.price, tick), l.qty) for l in (*s.bids, *s.asks)]
        for r, q in levels:
            if not row_lo <= r <= row_hi:
                continue
            i = r - row_lo
            if mode == "max":
                mat[i, c0:c1 + 1] = np.maximum(mat[i, c0:c1 + 1], q)
            else:
                for c in range(c0, c1 + 1):
                    lo, hi = max(start, c * dt_seconds), min(end, (c + 1) * dt_seconds)
                    mat[i, c] += q * max(0.0, hi - lo) / dt_seconds
    return Heatmap(t_start, dt_seconds, row_lo, tick, mat)


def intensity(matrix: np.ndarray, scale: Literal["linear", "log", "percentile"] = "log", clip_percentile: float = 99.0) -> np.ndarray:
    """Map quantities to [0, 1]. Large outliers are clipped at the clip percentile of non-zero
    cells, otherwise one huge wall would flatten the rest of the map to a single color."""
    out = np.zeros_like(matrix, dtype=np.float64)
    pos = matrix > 0
    if not pos.any():
        return out
    vals = matrix[pos]
    if scale == "percentile":
        order = np.argsort(np.argsort(vals))
        out[pos] = (order + 1) / len(vals)
        return out
    cap = float(np.percentile(vals, clip_percentile)) or float(vals.max())
    clipped = np.minimum(matrix, cap)
    if scale == "linear":
        out[pos] = clipped[pos] / cap
    else:
        out[pos] = np.log1p(clipped[pos]) / np.log1p(cap)
    return np.clip(out, 0.0, 1.0)


# Cool to warm: the more liquidity, the warmer the color. Mirrors the convention used by
# common liquidity heatmaps (dark blue = thin, red = thick). Front end uses identical stops.
COLOR_STOPS: tuple[tuple[float, tuple[int, int, int]], ...] = (
    (0.00, (8, 16, 48)),
    (0.25, (24, 80, 160)),
    (0.50, (40, 170, 160)),
    (0.75, (240, 200, 60)),
    (1.00, (220, 50, 40)),
)


def color_at(x: float) -> tuple[int, int, int]:
    x = min(1.0, max(0.0, x))
    for (a, ca), (b, cb) in zip(COLOR_STOPS, COLOR_STOPS[1:]):
        if x <= b:
            f = 0.0 if b == a else (x - a) / (b - a)
            return tuple(int(round(ca[i] + f * (cb[i] - ca[i]))) for i in range(3))  # type: ignore[return-value]
    return COLOR_STOPS[-1][1]
