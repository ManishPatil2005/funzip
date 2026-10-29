import { dayKey } from "../lib/format";
import { idxToX, priceToY, visibleRange, type PlotRect, type Viewport } from "../lib/viewport";
import type { FootprintBarDTO, SessionProfileDTO } from "../lib/types";
import { rgba, T } from "./theme";

/** Plain OHLC candles, optionally dimmed (used under TPO letters). */
export function drawCandles(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect, alpha = 1): void {
  const [i0, i1] = visibleRange(v, r, bars.length);
  const bw = Math.max(1, Math.min(v.spacing * 0.62, 40));
  ctx.globalAlpha = alpha;
  for (let i = i0; i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const cx = Math.round(idxToX(v, r, i)) + 0.5;
    const col = b.close >= b.open ? T.up : T.dn;
    ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(cx, priceToY(v, r, b.high)); ctx.lineTo(cx, priceToY(v, r, b.low)); ctx.stroke();
    const yo = priceToY(v, r, b.open), yc = priceToY(v, r, b.close);
    ctx.fillRect(cx - bw / 2, Math.min(yo, yc), bw, Math.max(1, Math.abs(yc - yo)));
  }
  ctx.globalAlpha = 1;
}

/** Buy/sell volume bars along the bottom of the main pane (ask on the bottom in green, bid above in red). */
export function drawVolumeBars(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect, frac = 0.18): void {
  const [i0, i1] = visibleRange(v, r, bars.length);
  let max = 1;
  for (let i = i0; i <= i1; i++) max = Math.max(max, bars[i]?.volume ?? 0);
  const H = r.h * frac, bw = Math.max(1, v.spacing * 0.7);
  for (let i = i0; i <= i1; i++) {
    const b = bars[i];
    if (!b) continue;
    const cx = idxToX(v, r, i);
    const ha = (b.ask_volume / max) * H, hb = (b.bid_volume / max) * H;
    ctx.fillStyle = rgba(T.up, 0.55); ctx.fillRect(cx - bw / 2, r.y + r.h - ha, bw, ha);
    ctx.fillStyle = rgba(T.dn, 0.55); ctx.fillRect(cx - bw / 2, r.y + r.h - ha - hb, bw, hb);
  }
}

/** Session VWAP, broken at each new session so it never connects across the overnight gap. */
export function drawVWAP(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], v: Viewport, r: PlotRect): void {
  const [i0, i1] = visibleRange(v, r, bars.length);
  ctx.strokeStyle = T.vwap; ctx.lineWidth = 1.6; ctx.beginPath();
  let prevDay = "", pen = false;
  for (let i = Math.max(0, i0 - 1); i <= i1; i++) {
    const b = bars[i];
    if (!b || b.vwap === null) continue;
    const d = dayKey(Date.parse(b.ts_open));
    const x = idxToX(v, r, i), y = priceToY(v, r, b.vwap);
    if (d !== prevDay || !pen) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    prevDay = d; pen = true;
  }
  ctx.stroke();
}

/** Per-session volume profile anchored at the session's first bar, with POC and value-area lines running across the session. */
export function drawSessionProfiles(ctx: CanvasRenderingContext2D, bars: FootprintBarDTO[], tsMs: number[], profs: SessionProfileDTO[], v: Viewport, r: PlotRect): void {
  for (const p of profs) {
    const s = Date.parse(p.start), e = Date.parse(p.end);
    const first = tsMs.findIndex((t) => t >= s);
    if (first < 0) continue;
    let last = first;
    while (last + 1 < tsMs.length && tsMs[last + 1]! <= e) last++;
    const xL = idxToX(v, r, first) - v.spacing / 2, xR = idxToX(v, r, last) + v.spacing / 2;
    if (xR < r.x || xL > r.x + r.w) continue;
    const entries = Object.entries(p.rows).map(([k, [bid, ask]]) => ({ row: Number(k), vol: bid + ask }));
    const maxV = Math.max(1, ...entries.map((x) => x.vol));
    const maxLen = Math.min((xR - xL) * 0.45, 260);
    const rowPx = Math.abs(priceToY(v, r, 0.5 * p.tick) - priceToY(v, r, -0.5 * p.tick));
    const { poc, vah, val } = p.levels;
    for (const en of entries) {
      const price = en.row * p.tick;
      const inVA = price >= val - 1e-9 && price <= vah + 1e-9;
      ctx.fillStyle = inVA ? rgba("#3b82f6", 0.55) : rgba("#9ca3af", 0.42);
      ctx.fillRect(xL, priceToY(v, r, price + p.tick / 2), (en.vol / maxV) * maxLen, Math.max(1, rowPx - 0.5));
    }
    const line = (price: number, col: string, dash: number[], w: number) => {
      ctx.strokeStyle = col; ctx.lineWidth = w; ctx.setLineDash(dash);
      const y = priceToY(v, r, price); ctx.beginPath(); ctx.moveTo(xL, y); ctx.lineTo(xR, y); ctx.stroke(); ctx.setLineDash([]);
    };
    line(poc, "#ef4444", [], 1.6); line(vah, "#22c55e", [5, 4], 1); line(val, "#22c55e", [5, 4], 1);
  }
}

/** Composite profile of the visible bars at the right edge of the pane, with VA shading and POC. */
export function drawVisibleProfile(ctx: CanvasRenderingContext2D, prof: { tick: number; rows: { row: number; bid: number; ask: number }[]; levels: { poc: number; vah: number; val: number } | null }, v: Viewport, r: PlotRect): void {
  const maxV = Math.max(1, ...prof.rows.map((x) => x.bid + x.ask));
  const maxLen = Math.min(r.w * 0.16, 150), xR = r.x + r.w;
  const rowPx = Math.abs(priceToY(v, r, 0.5 * prof.tick) - priceToY(v, r, -0.5 * prof.tick));
  const lv = prof.levels;
  if (lv) { ctx.fillStyle = rgba("#3b82f6", 0.07); const y1 = priceToY(v, r, lv.vah + prof.tick / 2), y2 = priceToY(v, r, lv.val - prof.tick / 2); ctx.fillRect(r.x, y1, r.w, y2 - y1); }
  for (const x of prof.rows) {
    const price = x.row * prof.tick, y = priceToY(v, r, price + prof.tick / 2), h = Math.max(1, rowPx - 0.5);
    const inVA = lv ? price >= lv.val - 1e-9 && price <= lv.vah + 1e-9 : false;
    const lenA = (x.ask / maxV) * maxLen, lenB = (x.bid / maxV) * maxLen;
    ctx.fillStyle = inVA ? rgba("#22d3ee", 0.6) : rgba("#22d3ee", 0.3); ctx.fillRect(xR - lenA - lenB, y, lenA, h);
    ctx.fillStyle = inVA ? rgba("#f59e0b", 0.6) : rgba("#f59e0b", 0.3); ctx.fillRect(xR - lenB, y, lenB, h);
  }
  if (lv) {
    ctx.strokeStyle = T.poc; ctx.lineWidth = 1.5; const y = priceToY(v, r, lv.poc); ctx.beginPath(); ctx.moveTo(xR - maxLen - 8, y); ctx.lineTo(xR, y); ctx.stroke();
    ctx.setLineDash([4, 4]); ctx.strokeStyle = rgba("#22d3ee", 0.6); ctx.lineWidth = 1;
    for (const p of [lv.vah, lv.val]) { const yy = priceToY(v, r, p); ctx.beginPath(); ctx.moveTo(r.x, yy); ctx.lineTo(xR, yy); ctx.stroke(); }
    ctx.setLineDash([]);
  }
}
