import { idxToX, priceToY, type PlotRect, type Viewport } from "../lib/viewport";
import type { TPODTO } from "../lib/types";
import { periodColor, rgba, T } from "./theme";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";

/**
 * Market Profile: one letter per 30-minute period per price row, laid out left to right from the session's first bar.
 * Value area is shaded, the POC row is outlined, the initial balance (first two periods) is marked, single prints are dashed.
 */
export function drawTPO(ctx: CanvasRenderingContext2D, profs: TPODTO[], tsMs: number[], v: Viewport, r: PlotRect): void {
  for (let pi = 0; pi < profs.length; pi++) {
    const p = profs[pi]!;
    const s = Date.parse(p.start);
    const first = tsMs.findIndex((t) => t >= s);
    if (first < 0) continue;
    const nextStart = profs[pi + 1] ? Date.parse(profs[pi + 1]!.start) : Infinity;
    let last = first;
    while (last + 1 < tsMs.length && tsMs[last + 1]! < nextStart) last++;
    const xL = idxToX(v, r, first) - v.spacing / 2, xR = idxToX(v, r, last) + v.spacing / 2;
    if (xR < r.x || xL > r.x + r.w) continue;
    const rowPx = Math.abs(priceToY(v, r, 0.5 * p.tick) - priceToY(v, r, -0.5 * p.tick));
    const cw = Math.max(6, Math.min(rowPx * 0.95, 18));
    const fs = Math.max(7, Math.min(Math.floor(rowPx * 0.75), 12));
    const lv = p.levels;
    // value-area band across the session
    ctx.fillStyle = rgba("#facc15", 0.07);
    const yv1 = priceToY(v, r, lv.vah + p.tick / 2), yv2 = priceToY(v, r, lv.val - p.tick / 2);
    ctx.fillRect(xL, yv1, xR - xL, yv2 - yv1);
    ctx.font = `${fs}px ${T.mono}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    for (const [k, str] of Object.entries(p.letters)) {
      const row = Number(k), y = priceToY(v, r, (row + 0.5) * p.tick), h = Math.max(1, rowPx - 1);
      const isPoc = Math.abs(row * p.tick - lv.poc) < p.tick / 2;
      for (let j = 0; j < str.length; j++) {
        const ch = str[j]!, x = xL + j * cw;
        ctx.fillStyle = isPoc ? "#a21caf" : periodColor(LETTERS.indexOf(ch));
        ctx.fillRect(x, y, cw - 1, h);
        if (rowPx >= 9 && cw >= 8) { ctx.fillStyle = "#fff"; ctx.fillText(ch, x + (cw - 1) / 2, y + h / 2 + 0.5); }
      }
    }
    // POC line, IB, single prints
    const hl = (price: number, col: string, dash: number[], w: number) => {
      ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash(dash);
      const y = priceToY(v, r, price); ctx.beginPath(); ctx.moveTo(xL, y); ctx.lineTo(xR, y); ctx.stroke(); ctx.setLineDash([]);
    };
    hl(lv.poc, "#d946ef", [], 1.4); hl(lv.vah, "#84cc16", [6, 4], 1); hl(lv.val, "#84cc16", [6, 4], 1);
    if (lv.ib_high !== null) hl(lv.ib_high, rgba("#38bdf8", 0.7), [2, 3], 1);
    if (lv.ib_low !== null) hl(lv.ib_low, rgba("#38bdf8", 0.7), [2, 3], 1);
    ctx.strokeStyle = "#fde047"; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
    for (const [a, b] of lv.single_print_ranges) {
      const y1 = priceToY(v, r, b + p.tick / 2), y2 = priceToY(v, r, a - p.tick / 2);
      ctx.strokeRect(xL + 0.5, y1, Math.max(cw, 8), y2 - y1);
    }
    ctx.setLineDash([]);
  }
}
