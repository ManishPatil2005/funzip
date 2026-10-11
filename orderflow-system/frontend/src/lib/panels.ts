import { colorAt } from "./color";
import type { FootprintBarDTO } from "./types";

export interface ProfileBar { row: number; y: number; h: number; w: number; isPoc: boolean; inValueArea: boolean }

/** Horizontal volume-profile bars anchored at the right edge. Width is proportional to volume. */
export function profileBars(rows: Record<string, number>, levels: { poc_row: number; vah_row: number; val_row: number },
  tick: number, priceToY: (p: number) => number | null, maxWidth: number): ProfileBar[] {
  const peak = Math.max(1, ...Object.values(rows));
  const out: ProfileBar[] = [];
  for (const [k, v] of Object.entries(rows)) {
    const row = Number(k);
    const top = priceToY((row + 0.5) * tick), bottom = priceToY((row - 0.5) * tick);
    if (top === null || bottom === null) continue;
    out.push({ row, y: Math.min(top, bottom), h: Math.abs(bottom - top), w: (v / peak) * maxWidth,
      isPoc: row === levels.poc_row, inValueArea: row >= levels.val_row && row <= levels.vah_row });
  }
  return out;
}

/** CVD line points; a new segment starts where the session resets (cvd_open back to 0 after a non-zero close). */
export function cvdSegments(bars: FootprintBarDTO[], width: number, height: number, pad = 8): { x: number; y: number }[][] {
  if (!bars.length) return [];
  const vals = bars.flatMap((b) => [b.cvd_open, b.cvd_close]);
  const lo = Math.min(...vals), hi = Math.max(...vals), span = hi - lo || 1;
  const segs: { x: number; y: number }[][] = [[]];
  bars.forEach((b, i) => {
    const prev = bars[i - 1];
    if (prev && b.cvd_open === 0 && prev.cvd_close !== 0) segs.push([]);
    const x = bars.length === 1 ? width / 2 : (i / (bars.length - 1)) * width;
    segs[segs.length - 1]!.push({ x, y: pad + (1 - (b.cvd_close - lo) / span) * (height - 2 * pad) });
  });
  return segs;
}

/** RGBA pixel buffer (rows x cols, top row = highest price) from backend intensity values in [0,1]. */
export function heatmapPixels(intensity: number[][]): { width: number; height: number; data: Uint8ClampedArray } {
  const height = intensity.length, width = height ? intensity[0]!.length : 0;
  const data = new Uint8ClampedArray(width * height * 4);
  for (let r = 0; r < height; r++) {
    const src = intensity[height - 1 - r]!; // flip so higher prices are drawn at the top
    for (let c = 0; c < width; c++) {
      const [R, G, B] = colorAt(src[c]!);
      const i = (r * width + c) * 4;
      data[i] = R; data[i + 1] = G; data[i + 2] = B; data[i + 3] = 255;
    }
  }
  return { width, height, data };
}
