import type { ConePoint, DayLevels } from "../lib/levels";
import { fmtPrice } from "../lib/format";
import { idxToX, priceToY, type PlotRect, type Viewport } from "../lib/viewport";
import { rgba, T } from "./theme";

interface Line { label: string; price: number | null; color: string; dash: number[] }

/** Horizontal reference lines for the previous day (H/L/C, POC/VAH/VAL) and today's open, labelled at the left edge. */
export function drawLevels(ctx: CanvasRenderingContext2D, lv: DayLevels, v: Viewport, r: PlotRect, tick: number): void {
  const lines: Line[] = [
    { label: "pdH", price: lv.high, color: "#94a3b8", dash: [2, 3] }, { label: "pdL", price: lv.low, color: "#94a3b8", dash: [2, 3] },
    { label: "pdC", price: lv.close, color: "#64748b", dash: [2, 3] },
    { label: "pPOC", price: lv.poc, color: T.poc, dash: [6, 3] }, { label: "pVAH", price: lv.vah, color: "#38bdf8", dash: [6, 3] }, { label: "pVAL", price: lv.val, color: "#38bdf8", dash: [6, 3] },
    { label: "dOpen", price: lv.todayOpen, color: "#a78bfa", dash: [1, 3] },
  ];
  ctx.save();
  ctx.font = `10px ${T.mono}`; ctx.textAlign = "left"; ctx.textBaseline = "bottom"; ctx.lineWidth = 1;
  for (const l of lines) {
    if (l.price === null) continue;
    const y = Math.round(priceToY(v, r, l.price)) + 0.5;
    if (y < r.y || y > r.y + r.h) continue;
    ctx.strokeStyle = rgba(l.color, 0.75); ctx.setLineDash(l.dash);
    ctx.beginPath(); ctx.moveTo(r.x, y); ctx.lineTo(r.x + r.w, y); ctx.stroke();
    ctx.setLineDash([]); ctx.fillStyle = l.color;
    ctx.fillText(`${l.label} ${fmtPrice(l.price, tick)}`, r.x + 6, y - 1);
  }
  ctx.restore();
}

/** Volatility cone to the right of the last bar: shaded ±1σ and ±2σ bands. Statistical range only (see lib/levels.ts). */
export function drawCone(ctx: CanvasRenderingContext2D, cone: ConePoint[], lastIdx: number, lastClose: number, v: Viewport, r: PlotRect): void {
  if (!cone.length) return;
  const x0 = idxToX(v, r, lastIdx), y0 = priceToY(v, r, lastClose);
  const pts = (key: "up1" | "dn1" | "up2" | "dn2") => cone.map((c) => [idxToX(v, r, lastIdx + c.k), priceToY(v, r, c[key])] as const);
  const band = (up: ReturnType<typeof pts>, dn: ReturnType<typeof pts>, fill: string) => {
    ctx.beginPath(); ctx.moveTo(x0, y0);
    for (const [x, y] of up) ctx.lineTo(x, y);
    for (const [x, y] of [...dn].reverse()) ctx.lineTo(x, y);
    ctx.closePath(); ctx.fillStyle = fill; ctx.fill();
  };
  ctx.save();
  band(pts("up2"), pts("dn2"), rgba(T.accent, 0.07));
  band(pts("up1"), pts("dn1"), rgba(T.accent, 0.12));
  ctx.strokeStyle = rgba(T.accent, 0.6); ctx.lineWidth = 1;
  for (const k of ["up1", "dn1"] as const) { ctx.beginPath(); ctx.moveTo(x0, y0); pts(k).forEach(([x, y]) => ctx.lineTo(x, y)); ctx.stroke(); }
  const end = cone[cone.length - 1]!;
  ctx.font = `10px ${T.mono}`; ctx.fillStyle = T.accent; ctx.textAlign = "right"; ctx.textBaseline = "middle";
  const ex = idxToX(v, r, lastIdx + end.k);
  ctx.fillText(`±1σ ${fmtPrice(end.up1, 0.01)} / ${fmtPrice(end.dn1, 0.01)}`, ex - 4, priceToY(v, r, end.up1) - 8);
  ctx.restore();
}
