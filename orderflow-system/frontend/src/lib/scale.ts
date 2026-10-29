/** "Nice" axis ticks: step is 1, 2, 2.5 or 5 times a power of ten. */
export function niceTicks(lo: number, hi: number, target = 8): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / Math.max(1, target);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const step = ([1, 2, 2.5, 5, 10].map((m) => m * pow).find((s) => s >= raw) ?? 10 * pow);
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}

/** Row sizes a trader would pick, all exact multiples of the instrument's tick (0.05 -> 0.05, 0.1, 0.25, 0.5, 1, 2, 2.5, 5 ...). */
export function rowLadder(baseTick: number, maxSize = baseTick * 4000): number[] {
  const out: number[] = [];
  for (let e = -4; e <= 6; e++) {
    for (const m of [1, 2, 2.5, 5]) {
      const v = Number((m * 10 ** e).toPrecision(12));
      const k = v / baseTick;
      if (v >= baseTick - 1e-12 && v <= maxSize && Math.abs(k - Math.round(k)) < 1e-9) out.push(v);
    }
  }
  return out;
}

/**
 * Smallest ladder size whose rows are at least `minRowPx` tall for the visible price span.
 * This is what keeps the numbers readable: rows are merged until the text fits.
 */
export function pickRowSize(baseTick: number, visiblePriceSpan: number, plotHeightPx: number, minRowPx = 15): number {
  const ladder = rowLadder(baseTick);
  if (!(visiblePriceSpan > 0) || !(plotHeightPx > 0)) return ladder[0] ?? baseTick;
  const need = (minRowPx * visiblePriceSpan) / plotHeightPx;
  return ladder.find((v) => v >= need - 1e-12) ?? ladder[ladder.length - 1] ?? baseTick;
}
