import type { PlotRect } from "../lib/viewport";

export const AXIS_W = 72, TIME_H = 24, STATS_ROW_H = 20, STATS_ROWS = 4, DELTA_H = 120;

export interface PaneLayout { w: number; h: number; main: PlotRect; stats: PlotRect | null; delta: PlotRect | null; time: PlotRect; axisX: number }

/** Panes stack top to bottom: main, bar statistics, delta bars, time axis. All share the same x range; the price axis is the right gutter. */
export const MIN_MAIN_H = 200;

/**
 * Panes stack top to bottom: main, bar statistics, delta bars, time axis. All share one x range; the price axis is the right gutter.
 * In short panes the main chart has priority: the delta pane is dropped first, then the stats table, so footprint numbers stay legible.
 */
export function layoutPanes(w: number, h: number, o: { stats: boolean; delta: boolean }): PaneLayout {
  const pw = Math.max(50, w - AXIS_W);
  let showStats = o.stats, showDelta = o.delta;
  const mainFor = () => h - TIME_H - (showStats ? STATS_ROW_H * STATS_ROWS : 0) - (showDelta ? DELTA_H : 0);
  if (mainFor() < MIN_MAIN_H) showDelta = false;
  if (mainFor() < MIN_MAIN_H) showStats = false;
  const statsH = showStats ? STATS_ROW_H * STATS_ROWS : 0, deltaH = showDelta ? DELTA_H : 0;
  const mainH = Math.max(60, h - TIME_H - statsH - deltaH);
  const main = { x: 0, y: 0, w: pw, h: mainH };
  const stats = showStats ? { x: 0, y: mainH, w: pw, h: statsH } : null;
  const delta = showDelta ? { x: 0, y: mainH + statsH, w: pw, h: deltaH } : null;
  return { w, h, main, stats, delta, time: { x: 0, y: mainH + statsH + deltaH, w: pw, h: TIME_H }, axisX: pw };
}
