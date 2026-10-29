import { fmtVol } from "../lib/format";
import { idxToX, priceToY, visibleRange, xToIdx, type PlotRect, type Viewport } from "../lib/viewport";
import type { FootprintBarDTO } from "../lib/types";
import { rgba, T } from "./theme";

export interface FpOpts { imbalance: boolean }
export interface CellHit { barIdx: number; row: number; bid: number; ask: number; price: number }

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

/**
 * Numeric footprint: sell (bid) volume left of the wick, buy (ask) volume right, one row per price level.
 * Numbers are drawn only when they fit (row height and half-width); otherwise cells fall back to colour only.
 * Row size is chosen upstream so rows are tall enough, which is what makes the numbers legible.
 */
export function drawFootprint(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect, o: FpOpts, hover: CellHit | null): void {
  const [i0, i1] = visibleRange(v, r, bars.length);
  const slot = v.spacing;
  const gap = clamp(slot * 0.06, 2, 8);
  const bw = Math.max(2, slot - gap);
  for (let i = i0; i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const cx = idxToX(v, r, i);
    const x0 = cx - bw / 2, half = bw / 2 - 1;
    const rowPx = Math.abs(priceToY(v, r, 0.5 * b.tick) - priceToY(v, r, -0.5 * b.tick));
    const fs = clamp(Math.floor(rowPx * 0.7), 8, 12);
    const canText = rowPx >= 10 && half >= fs * 3.1;
    const entries = Object.entries(b.rows).map(([k, [bid, ask]]) => ({ row: Number(k), bid, ask }));
    const maxV = Math.max(1, ...entries.map((e) => Math.max(e.bid, e.ask)));
    const imbAsk = new Set(b.imbalances.filter((m) => m.side === "ask").map((m) => m.row));
    const imbBid = new Set(b.imbalances.filter((m) => m.side === "bid").map((m) => m.row));
    const top = (row: number) => priceToY(v, r, (row + 0.5) * b.tick);

    // wick first so cells sit on top of it
    const up = b.close >= b.open;
    ctx.strokeStyle = up ? T.up : T.dn; ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(cx, priceToY(v, r, b.high + b.tick / 2)); ctx.lineTo(cx, priceToY(v, r, b.low - b.tick / 2)); ctx.stroke();

    ctx.font = `${fs}px ${T.mono}`; ctx.textBaseline = "middle";
    for (const e of entries) {
      const y = top(e.row), h = Math.max(1, rowPx - 1);
      const sellW = half * (0.1 + 0.9 * (e.bid / maxV)), buyW = half * (0.1 + 0.9 * (e.ask / maxV));
      const flagBid = o.imbalance && imbBid.has(e.row), flagAsk = o.imbalance && imbAsk.has(e.row);
      if (e.bid > 0) { ctx.fillStyle = flagBid ? rgba(T.imb, 0.75) : rgba(T.dn, 0.18 + 0.4 * (e.bid / maxV)); ctx.fillRect(cx - 1 - sellW, y, sellW, h); }
      if (e.ask > 0) { ctx.fillStyle = flagAsk ? rgba(T.imb, 0.75) : rgba(T.up, 0.18 + 0.4 * (e.ask / maxV)); ctx.fillRect(cx + 1, y, buyW, h); }
      if (flagBid) { ctx.strokeStyle = T.imb; ctx.lineWidth = 1; ctx.strokeRect(cx - 1 - sellW + 0.5, y + 0.5, sellW - 1, h - 1); }
      if (flagAsk) { ctx.strokeStyle = T.imb; ctx.lineWidth = 1; ctx.strokeRect(cx + 1.5, y + 0.5, buyW - 1, h - 1); }
      if (canText) {
        ctx.fillStyle = flagBid ? "#fff" : T.textBright; ctx.font = `${flagBid ? "bold " : ""}${fs}px ${T.mono}`;
        ctx.textAlign = "right"; ctx.fillText(fmtVol(e.bid), cx - 4, y + h / 2 + 0.5);
        ctx.fillStyle = flagAsk ? "#fff" : T.textBright; ctx.font = `${flagAsk ? "bold " : ""}${fs}px ${T.mono}`;
        ctx.textAlign = "left"; ctx.fillText(fmtVol(e.ask), cx + 4, y + h / 2 + 0.5);
      }
    }
    // stacked imbalances: one thick outline around the run
    if (o.imbalance) {
      ctx.lineWidth = 2; ctx.strokeStyle = "#e0f2fe";
      for (const s of b.stacked) {
        const yT = top(s.high_row), yB = top(s.low_row - 1);
        if (s.side === "ask") ctx.strokeRect(cx + 1, yT, half, yB - yT); else ctx.strokeRect(cx - 1 - half, yT, half, yB - yT);
      }
    }
    // point of control
    const pocTop = top(b.poc_row);
    ctx.strokeStyle = T.poc; ctx.lineWidth = 1.5; ctx.strokeRect(x0 + 0.5, pocTop + 0.5, bw - 1, Math.max(1, rowPx - 1));
    // running-delta extremes above/below the bar (labelled for what they are)
    if (bw >= 64) {
      ctx.font = `10px ${T.mono}`; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
      ctx.fillStyle = T.up; ctx.fillText(`Δ↑ ${fmtVol(b.delta_max)}`, cx, priceToY(v, r, b.high + b.tick / 2) - 4);
      ctx.fillStyle = T.dn; ctx.textBaseline = "top"; ctx.fillText(`Δ↓ ${fmtVol(b.delta_min)}`, cx, priceToY(v, r, b.low - b.tick / 2) + 3);
      ctx.textBaseline = "middle";
    }
    if (hover && hover.barIdx === i) {
      ctx.strokeStyle = "#fff"; ctx.lineWidth = 1;
      ctx.strokeRect(x0 + 0.5, top(hover.row) + 0.5, bw - 1, Math.max(1, rowPx - 1));
    }
  }
}

/** Which cell is under the pointer (null outside bars/rows). */
export function hitCell(bars: FootprintBarDTO[], v: Viewport, r: PlotRect, x: number, y: number, yToP: (y: number) => number): CellHit | null {
  const i = Math.round(xToIdx(v, r, x));
  const b = bars[i];
  if (!b) return null;
  const price = yToP(y), row = Math.round(price / b.tick);
  const c = b.rows[String(row)];
  if (!c) return null;
  return { barIdx: i, row, bid: c[0], ask: c[1], price: row * b.tick };
}
