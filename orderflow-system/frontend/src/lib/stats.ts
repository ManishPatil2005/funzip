import type { FootprintBarDTO } from "./types";

export interface BarStat { volume: number; delta: number; deltaPct: number; cvd: number }

export const barStat = (b: FootprintBarDTO): BarStat => ({
  volume: b.volume, delta: b.delta, deltaPct: b.volume > 0 ? b.delta / b.volume : 0, cvd: b.cvd_close,
});

/** Intensity 0..1 of `v` against the largest magnitude in `all` (square-root scaled so mid values stay visible). */
export function intensity(v: number, all: number[]): number {
  const m = Math.max(1e-12, ...all.map(Math.abs));
  return Math.sqrt(Math.min(1, Math.abs(v) / m));
}

/** Delta-bar candle (cumulative delta): open/close are CVD at the bar's edges, wicks are the running-delta extremes. */
export function deltaCandle(b: FootprintBarDTO) {
  return { open: b.cvd_open, close: b.cvd_close, high: b.cvd_open + b.delta_max, low: b.cvd_open + b.delta_min };
}
