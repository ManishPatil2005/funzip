import { dayKey, fmtClock, fmtDay, fmtPct, fmtPrice, fmtSigned, fmtVol } from "../lib/format";
import { niceTicks } from "../lib/scale";
import { barStat, deltaCandle, intensity } from "../lib/stats";
import { idxToX, priceToY, visibleRange, type PlotRect, type Viewport } from "../lib/viewport";
import type { FootprintBarDTO } from "../lib/types";
import { AXIS_W, STATS_ROW_H, type PaneLayout } from "./layout";
import { rgba, T } from "./theme";

/** Horizontal grid lines (call inside the pane's clip). */
export function drawGrid(ctx: CanvasRenderingContext2D, v: Viewport, r: PlotRect): void {
  for (const p of niceTicks(v.lo, v.hi, Math.max(3, Math.floor(r.h / 46)))) {
    const y = Math.round(priceToY(v, r, p)) + 0.5;
    ctx.strokeStyle = T.grid; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(r.x, y); ctx.lineTo(r.x + r.w, y); ctx.stroke();
  }
}

/** Right-hand price labels (call outside the clip: they live in the axis gutter). */
export function drawPriceLabels(ctx: CanvasRenderingContext2D, v: Viewport, r: PlotRect, tick: number, axisX: number): void {
  ctx.font = `11px ${T.mono}`; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillStyle = T.text;
  for (const p of niceTicks(v.lo, v.hi, Math.max(3, Math.floor(r.h / 46)))) ctx.fillText(fmtPrice(p, Math.min(tick, 1)), axisX + 6, priceToY(v, r, p));
}

export function priceTag(ctx: CanvasRenderingContext2D, text: string, y: number, axisX: number, bg: string): void {
  ctx.fillStyle = bg; ctx.fillRect(axisX, y - 9, AXIS_W, 18);
  ctx.fillStyle = "#fff"; ctx.font = `bold 11px ${T.mono}`; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(text, axisX + 6, y + 0.5);
}

/** Time axis labels, session separators drawn through every pane, date at each session start. */
export function drawTimeAxis(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, L: PaneLayout): void {
  const r = L.time, plotBottom = L.time.y;
  const [i0, i1] = visibleRange(v, L.main, bars.length);
  ctx.font = `11px ${T.mono}`; ctx.textBaseline = "middle"; ctx.textAlign = "center";
  const minGap = 74; let lastLabelX = -1e9;
  for (let i = Math.max(0, i0); i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const ms = Date.parse(b.ts_open), x = idxToX(v, L.main, i);
    const newDay = i === 0 || dayKey(Date.parse(bars[i - 1]!.ts_open)) !== dayKey(ms);
    if (newDay) {
      ctx.strokeStyle = T.gridStrong; ctx.setLineDash([3, 4]); ctx.beginPath(); ctx.moveTo(x - v.spacing / 2, 0); ctx.lineTo(x - v.spacing / 2, plotBottom); ctx.stroke(); ctx.setLineDash([]);
      ctx.fillStyle = T.textBright; ctx.font = `bold 11px ${T.mono}`; ctx.fillText(fmtDay(ms), x + 28, r.y + r.h / 2); ctx.font = `11px ${T.mono}`; lastLabelX = x + 28;
    } else if (x - lastLabelX >= minGap) {
      ctx.fillStyle = T.text; ctx.fillText(fmtClock(ms), x, r.y + r.h / 2); lastLabelX = x;
    }
  }
}

const cellBg = (v: number, all: number[], up = true): string => {
  const k = intensity(v, all);
  return v === 0 ? rgba("#94a3b8", 0.25) : rgba(v > 0 ? (up ? "#16a34a" : "#16a34a") : "#dc2626", 0.28 + 0.62 * k);
};

/** Bar statistics: Volume, Delta, Delta %, Cumulative delta - one cell per bar, aligned under the footprint. */
export function drawStatsTable(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect): void {
  const [i0, i1] = visibleRange(v, r, bars.length);
  const vis = bars.slice(i0, i1 + 1).map(barStat);
  const vols = vis.map((s) => s.volume), deltas = vis.map((s) => s.delta), pcts = vis.map((s) => s.deltaPct), cvds = vis.map((s) => s.cvd);
  const labels = ["Volume", "Delta", "Delta %", "Cum Δ"];
  ctx.fillStyle = T.panel; ctx.fillRect(r.x, r.y, r.w, r.h);
  const bw = Math.max(1, v.spacing - 1), fs = Math.min(11, Math.max(8, Math.floor(bw / 6)));
  ctx.font = `${fs}px ${T.mono}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  for (let i = i0; i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const s = barStat(b), x = idxToX(v, r, i) - bw / 2;
    const cells: [string, string][] = [
      [rgba("#6366f1", 0.18 + 0.7 * Math.sqrt(s.volume / Math.max(1, ...vols))), fmtVol(s.volume)],
      [cellBg(s.delta, deltas), fmtSigned(s.delta)],
      [cellBg(s.deltaPct, pcts), fmtPct(s.deltaPct)],
      [cellBg(s.cvd, cvds), fmtSigned(s.cvd)],
    ];
    cells.forEach(([bg, text], k) => {
      const y = r.y + k * STATS_ROW_H;
      ctx.fillStyle = bg; ctx.fillRect(x, y + 1, bw, STATS_ROW_H - 2);
      if (bw >= 38) { ctx.fillStyle = "#fff"; ctx.fillText(text, x + bw / 2, y + STATS_ROW_H / 2 + 0.5); }
    });
  }
  ctx.font = `bold 10px ${T.mono}`; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  labels.forEach((t, k) => { ctx.fillStyle = T.text; ctx.fillText(t, r.x + r.w + 6, r.y + k * STATS_ROW_H + STATS_ROW_H / 2); });
}

/** Delta bars: candles of cumulative delta (open/close = CVD at the bar edges, wicks = running-delta extremes). Own y-scale. */
export function drawDeltaBars(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect, axisX: number): { lo: number; hi: number } {
  const [i0, i1] = visibleRange(v, r, bars.length);
  let lo = Infinity, hi = -Infinity;
  for (let i = i0; i <= i1; i++) { const b = bars[i]; if (!b) continue; const c = deltaCandle(b); lo = Math.min(lo, c.low); hi = Math.max(hi, c.high); }
  if (!isFinite(lo)) { lo = -1; hi = 1; }
  lo = Math.min(lo, 0); hi = Math.max(hi, 0);
  const pad = (hi - lo) * 0.08 || 1; lo -= pad; hi += pad;
  const dv: Viewport = { ...v, lo, hi };
  ctx.fillStyle = T.panel; ctx.fillRect(r.x, r.y, r.w, r.h);
  ctx.save(); ctx.beginPath(); ctx.rect(r.x, r.y, r.w, r.h); ctx.clip();
  const ticks = niceTicks(lo, hi, 4);
  ctx.font = `10px ${T.mono}`; ctx.textAlign = "left"; ctx.textBaseline = "middle";
  for (const t of ticks) { const y = Math.round(priceToY(dv, r, t)) + 0.5; ctx.strokeStyle = T.grid; ctx.beginPath(); ctx.moveTo(r.x, y); ctx.lineTo(r.x + r.w, y); ctx.stroke(); }
  const y0 = priceToY(dv, r, 0); ctx.strokeStyle = "#7c2d12"; ctx.setLineDash([5, 4]); ctx.beginPath(); ctx.moveTo(r.x, y0); ctx.lineTo(r.x + r.w, y0); ctx.stroke(); ctx.setLineDash([]);
  const bw = Math.max(1, Math.min(v.spacing * 0.62, 40));
  for (let i = i0; i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const c = deltaCandle(b), cx = Math.round(idxToX(v, r, i)) + 0.5, col = c.close >= c.open ? T.up : T.dn;
    ctx.strokeStyle = col; ctx.fillStyle = col;
    ctx.beginPath(); ctx.moveTo(cx, priceToY(dv, r, c.high)); ctx.lineTo(cx, priceToY(dv, r, c.low)); ctx.stroke();
    const yo = priceToY(dv, r, c.open), yc = priceToY(dv, r, c.close);
    ctx.fillRect(cx - bw / 2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yc - yo)));
  }
  ctx.restore();
  ctx.font = `10px ${T.mono}`; ctx.fillStyle = T.text; ctx.textAlign = "left";
  for (const t of ticks) ctx.fillText(fmtVol(t), axisX + 6, priceToY(dv, r, t));
  ctx.font = `bold 11px ${T.mono}`; ctx.fillStyle = T.textBright; ctx.textAlign = "left"; ctx.fillText("Delta bars (cumulative, resets each session)", r.x + 8, r.y + 12);
  return { lo, hi };
}

export function drawCrosshair(ctx: CanvasRenderingContext2D, L: PaneLayout, x: number, y: number, priceText: string | null, timeText: string | null): void {
  ctx.save(); ctx.strokeStyle = "rgba(226,232,240,0.45)"; ctx.setLineDash([4, 4]); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, 0); ctx.lineTo(Math.round(x) + 0.5, L.time.y); ctx.stroke();
  if (priceText) { ctx.beginPath(); ctx.moveTo(0, Math.round(y) + 0.5); ctx.lineTo(L.axisX, Math.round(y) + 0.5); ctx.stroke(); }
  ctx.restore();
  if (priceText) priceTag(ctx, priceText, y, L.axisX, "#334155");
  if (timeText) { ctx.font = `bold 11px ${T.mono}`; const w = ctx.measureText(timeText).width + 14; ctx.fillStyle = "#334155"; ctx.fillRect(Math.min(Math.max(0, x - w / 2), L.axisX - w), L.time.y + 3, w, 18); ctx.fillStyle = "#fff"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(timeText, Math.min(Math.max(w / 2, x), L.axisX - w / 2), L.time.y + 12.5); }
}

/** OHLC legend line for the hovered (or latest) bar. */
export function drawLegend(ctx: CanvasRenderingContext2D, b: FootprintBarDTO | undefined, head: string, tick: number, x: number, y: number, maxX = Infinity): void {
  ctx.font = `bold 12px ${T.sans}`; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillStyle = T.textBright;
  ctx.fillText(head, x, y);
  if (!b) return;
  let cx = x + ctx.measureText(head).width + 14;
  const col = b.close >= b.open ? T.up : T.dn;
  const parts: [string, string, string][] = [
    ["O", fmtPrice(b.open, tick), col], ["H", fmtPrice(b.high, tick), col], ["L", fmtPrice(b.low, tick), col], ["C", fmtPrice(b.close, tick), col],
    ["Vol", fmtVol(b.volume), T.textBright], ["Buy", fmtVol(b.ask_volume), T.up], ["Sell", fmtVol(b.bid_volume), T.dn], ["Δ", fmtSigned(b.delta), b.delta >= 0 ? T.up : T.dn],
  ];
  ctx.font = `11px ${T.mono}`;
  for (const [k, val, c] of parts) {
    if (cx + ctx.measureText(`${k} ${val}`).width + 16 > maxX) break; // never run under the badges
    ctx.fillStyle = T.text; ctx.fillText(k, cx, y); cx += ctx.measureText(k).width + 4; ctx.fillStyle = c; ctx.fillText(val, cx, y); cx += ctx.measureText(val).width + 12; }
}
