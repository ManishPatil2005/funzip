import { profileFromBars } from "./profile";
import type { FootprintBarDTO } from "./types";

/** Reference levels from the previous trading day in `bars` (by calendar date of ts_open). Context, not a signal. */
export interface DayLevels {
  day: string; high: number; low: number; close: number;
  poc: number | null; vah: number | null; val: number | null; todayOpen: number | null;
}

const day = (b: FootprintBarDTO) => b.ts_open.slice(0, 10);

export function priorDayLevels(bars: FootprintBarDTO[]): DayLevels | null {
  if (bars.length < 2) return null;
  const today = day(bars[bars.length - 1]!);
  let end = bars.length - 1;
  while (end >= 0 && day(bars[end]!) === today) end--;
  if (end < 0) return null;
  const pd = day(bars[end]!);
  let start = end;
  while (start > 0 && day(bars[start - 1]!) === pd) start--;
  let high = -Infinity, low = Infinity;
  for (let i = start; i <= end; i++) { high = Math.max(high, bars[i]!.high); low = Math.min(low, bars[i]!.low); }
  const prof = profileFromBars(bars, start, end);
  const lv = prof?.levels;
  const tick = prof?.tick ?? 0;
  const toPx = (row: number | undefined) => (lv && row !== undefined ? row * tick : null);
  const firstToday = bars.findIndex((b) => day(b) === today);
  return {
    day: pd, high, low, close: bars[end]!.close,
    poc: toPx(lv?.poc), vah: toPx(lv?.vah), val: toPx(lv?.val),
    todayOpen: firstToday >= 0 ? bars[firstToday]!.open : null,
  };
}

export interface ConePoint { k: number; up1: number; dn1: number; up2: number; dn2: number }

/**
 * Volatility cone: ±1σ and ±2σ of the close, widening with sqrt(bars ahead).
 * ASSUMPTION (A16): intraday bar returns (overnight gaps excluded) are i.i.d. with zero mean, so the band is a statistical range, not a direction forecast
 * and not a probability of any trade outcome. Returns [] when there is too little history.
 */
export function volCone(bars: FootprintBarDTO[], horizon = 12, lookback = 60): ConePoint[] {
  const w = bars.slice(-(lookback + 1)).filter((b) => b.close > 0);
  const closes = w.map((b) => b.close);
  const rets: number[] = [];
  // overnight gaps are not intraday bar-to-bar moves: returns that cross a calendar day are excluded
  for (let i = 1; i < w.length; i++) if (day(w[i]!) === day(w[i - 1]!)) rets.push(Math.log(closes[i]! / closes[i - 1]!));
  if (rets.length < 10) return [];
  const mean = rets.reduce((a, b) => a + b, 0) / rets.length;
  const sd = Math.sqrt(rets.reduce((a, b) => a + (b - mean) ** 2, 0) / (rets.length - 1));
  const last = closes[closes.length - 1]!;
  const out: ConePoint[] = [];
  for (let k = 1; k <= horizon; k++) {
    const s = sd * Math.sqrt(k) * last;
    out.push({ k, up1: last + s, dn1: last - s, up2: last + 2 * s, dn2: last - 2 * s });
  }
  return out;
}

/** Replay cursor maths, kept pure so it is testable: next visible-bar count after one step, clamped to [min, total]. */
export function stepReplay(current: number, total: number, delta = 1, min = 1): number {
  return Math.max(min, Math.min(total, current + delta));
}
