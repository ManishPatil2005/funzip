import type { FootprintBarDTO } from "./types";

/** Bars are laid out by index (not by clock time) so overnight and weekend gaps collapse, as on every order-flow platform. */
export interface Viewport {
  spacing: number; // px per bar slot
  rightIdx: number; // fractional index of the bar at the right edge of the plot
  lo: number; hi: number; // visible price range
  autoY: boolean;
}

export interface PlotRect { x: number; y: number; w: number; h: number }

export const MIN_SPACING = 4, MAX_SPACING = 400;

export const idxToX = (v: Viewport, r: PlotRect, i: number): number => r.x + r.w - (v.rightIdx - i) * v.spacing;
export const xToIdx = (v: Viewport, r: PlotRect, x: number): number => v.rightIdx - (r.x + r.w - x) / v.spacing;
export const priceToY = (v: Viewport, r: PlotRect, p: number): number => r.y + ((v.hi - p) / (v.hi - v.lo)) * r.h;
export const yToPrice = (v: Viewport, r: PlotRect, y: number): number => v.hi - ((y - r.y) / r.h) * (v.hi - v.lo);

export function visibleRange(v: Viewport, r: PlotRect, n: number): [number, number] {
  const first = Math.max(0, Math.floor(xToIdx(v, r, r.x) - 1));
  const last = Math.min(n - 1, Math.ceil(v.rightIdx + 1));
  return [first, last];
}

/** Zoom the time axis keeping the bar under `anchorX` fixed. */
export function zoomX(v: Viewport, r: PlotRect, factor: number, anchorX: number): Viewport {
  const spacing = Math.min(MAX_SPACING, Math.max(MIN_SPACING, v.spacing * factor));
  const idx = xToIdx(v, r, anchorX);
  return { ...v, spacing, rightIdx: idx + (r.x + r.w - anchorX) / spacing };
}

export function panX(v: Viewport, dxPx: number, n: number): Viewport {
  const rightIdx = Math.min(n - 1 + 12, Math.max(0, v.rightIdx - dxPx / v.spacing));
  return { ...v, rightIdx };
}

/** Zoom the price axis around the price under `anchorY`; switches to manual Y. */
export function zoomY(v: Viewport, r: PlotRect, factor: number, anchorY: number): Viewport {
  const p = yToPrice(v, r, anchorY);
  const f = anchorY === anchorY ? (anchorY - r.y) / r.h : 0.5;
  const span = (v.hi - v.lo) * factor;
  return { ...v, autoY: false, hi: p + f * span, lo: p - (1 - f) * span };
}

export function panY(v: Viewport, r: PlotRect, dyPx: number): Viewport {
  const dp = (dyPx / r.h) * (v.hi - v.lo);
  return { ...v, autoY: false, lo: v.lo + dp, hi: v.hi + dp };
}

/** Price range that fits the visible bars with padding. */
/** Extra room above (legend + delta labels) and below (delta labels) so nothing is drawn under the legend. */
export function autoRange(bars: FootprintBarDTO[], first: number, last: number, padTop = 0.1, padBottom = 0.08): [number, number] | null {
  let lo = Infinity, hi = -Infinity;
  for (let i = first; i <= last; i++) {
    const b = bars[i];
    if (!b) continue;
    lo = Math.min(lo, b.low); hi = Math.max(hi, b.high);
  }
  if (!isFinite(lo)) return null;
  const span = Math.max(hi - lo, 1e-9);
  return [lo - span * padBottom, hi + span * padTop];
}

/** Index of the bar slot under x, or null outside the data. */
export function barAt(v: Viewport, r: PlotRect, x: number, n: number): number | null {
  const i = Math.round(xToIdx(v, r, x));
  return i >= 0 && i < n ? i : null;
}
