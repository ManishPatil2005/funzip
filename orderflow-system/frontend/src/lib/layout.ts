import type { FootprintBarDTO } from "./types";

export interface CellRect {
  row: number; x: number; y: number; w: number; h: number;
  bid: number; ask: number; isPoc: boolean; imbalance: "ask" | "bid" | null; stacked: boolean;
}

export interface Geometry {
  /** left edge x and width of the bar column, in CSS pixels */
  x: number; width: number;
  /** y for a price (top edge of the row's price). Supplied by the chart's priceToCoordinate. */
  priceToY: (price: number) => number | null;
}

/** Rows are bid | ask halves with a centre gutter. Returns null when the bar is off-screen. */
export function cellRects(bar: FootprintBarDTO, g: Geometry): CellRect[] | null {
  const out: CellRect[] = [];
  for (const [rowKey, [bid, ask]] of Object.entries(bar.rows)) {
    const row = Number(rowKey);
    const top = g.priceToY((row + 0.5) * bar.tick);
    const bottom = g.priceToY((row - 0.5) * bar.tick);
    if (top === null || bottom === null) return null;
    const imb = bar.imbalances.find((i) => i.row === row)?.side ?? null;
    const stacked = bar.stacked.some((s) => row >= s.low_row && row <= s.high_row);
    out.push({ row, x: g.x, y: Math.min(top, bottom), w: g.width, h: Math.abs(bottom - top), bid, ask, isPoc: row === bar.poc_row, imbalance: imb, stacked });
  }
  return out;
}

/** Numbers are drawn only when they fit; below this the cell is colour-only (no clutter). */
export const MIN_TEXT_HEIGHT = 11;
export const MIN_TEXT_WIDTH = 46;
export const canDrawText = (r: Pick<CellRect, "h" | "w">) => r.h >= MIN_TEXT_HEIGHT && r.w >= MIN_TEXT_WIDTH;

export function compact(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

/** Bar column width from the time scale: spacing between bars minus a gap, never negative. */
export function barWidth(spacingPx: number, gapPx = 2): number {
  return Math.max(0, spacingPx - gapPx);
}
