import { fmtClock, fmtDay, fmtPrice, fmtVol, fmtSigned } from "../lib/format";
import { profileFromBars } from "../lib/profile";
import { autoRange, barAt, idxToX, priceToY, visibleRange, yToPrice, type PlotRect, type Viewport } from "../lib/viewport";
import type { FootprintBarDTO, SessionProfileDTO, TPODTO } from "../lib/types";
import { drawCandles, drawSessionProfiles, drawVisibleProfile, drawVolumeBars, drawVWAP } from "./candles";
import { drawFootprint, hitCell, type CellHit } from "./footprint";
import { layoutPanes, type PaneLayout } from "./layout";
import { drawCrosshair, drawDeltaBars, drawGrid, drawLegend, drawPriceLabels, drawStatsTable, drawTimeAxis, priceTag } from "./panes";
import { drawTPO } from "./tpo";
import { rgba, T } from "./theme";

export type Mode = "footprint" | "candles" | "tpo";
export interface SceneOpts { stats: boolean; delta: boolean; vwap: boolean; profile: boolean; imbalance: boolean; volume: boolean }

export interface SceneInput {
  w: number; h: number; bars: FootprintBarDTO[]; tsMs: number[]; vp: Viewport; mode: Mode; opts: SceneOpts;
  sessionProfiles: SessionProfileDTO[]; tpo: TPODTO[]; hover: { x: number; y: number } | null;
  head: string; instrTick: number; badges: { text: string; color: string }[]; message: string;
}

export interface SceneResult { layout: PaneLayout; vp: Viewport; hoverBar: number | null; hoverCell: CellHit | null; rangeFromData: boolean }

export function renderScene(ctx: CanvasRenderingContext2D, s: SceneInput): SceneResult {
  const L = layoutPanes(s.w, s.h, { stats: s.mode === "footprint" && s.opts.stats, delta: s.opts.delta });
  const { bars } = s;
  let vp = s.vp;
  const [i0, i1] = visibleRange(vp, L.main, bars.length);
  // auto range uses pixel-based padding: room for the legend above and the delta labels below
  let rangeFromData = !vp.autoY;
  if (vp.autoY) { const a = autoRange(bars, i0, i1, Math.max(0.06, 40 / L.main.h), Math.max(0.05, 22 / L.main.h)); if (a) { vp = { ...vp, lo: a[0], hi: a[1] }; rangeFromData = true; } }

  ctx.fillStyle = T.bg; ctx.fillRect(0, 0, s.w, s.h);
  drawTimeAxis(ctx, bars, vp, L);

  // hover resolution (done early so the footprint can highlight the cell)
  let hoverBar: number | null = null, hoverCell: CellHit | null = null;
  if (s.hover && s.hover.x >= 0 && s.hover.x <= L.axisX) {
    hoverBar = barAt(vp, L.main, s.hover.x, bars.length);
    if (s.mode === "footprint" && s.hover.y >= L.main.y && s.hover.y <= L.main.y + L.main.h) hoverCell = hitCell(bars, vp, L.main, s.hover.x, s.hover.y, (y) => yToPrice(vp, L.main, y));
  }

  // main pane
  ctx.save(); ctx.beginPath(); ctx.rect(L.main.x, L.main.y, L.main.w, L.main.h); ctx.clip();
  drawGrid(ctx, vp, L.main);
  if (s.mode === "footprint") {
    if (s.opts.profile) { const prof = profileFromBars(bars, i0, i1); if (prof) drawVisibleProfile(ctx, prof, vp, L.main); }
    if (s.opts.vwap) drawVWAP(ctx, bars, vp, L.main);
    drawFootprint(ctx, bars, vp, L.main, { imbalance: s.opts.imbalance }, hoverCell);
  } else if (s.mode === "candles") {
    if (s.opts.profile) drawSessionProfiles(ctx, bars, s.tsMs, s.sessionProfiles, vp, L.main);
    if (s.opts.volume) drawVolumeBars(ctx, bars, vp, L.main);
    drawCandles(ctx, bars, vp, L.main);
    if (s.opts.vwap) drawVWAP(ctx, bars, vp, L.main);
  } else {
    drawCandles(ctx, bars, vp, L.main, 0.45);
    drawTPO(ctx, s.tpo, s.tsMs, vp, L.main);
    if (s.opts.vwap) drawVWAP(ctx, bars, vp, L.main);
  }
  ctx.restore();
  drawPriceLabels(ctx, vp, L.main, s.instrTick, L.axisX);

  if (L.stats) drawStatsTable(ctx, bars, vp, L.stats);
  if (L.delta) drawDeltaBars(ctx, bars, vp, L.delta, L.axisX);

  // last price tag
  const last = bars[bars.length - 1];
  if (last) { const y = priceToY(vp, L.main, last.close); if (y >= 0 && y <= L.main.h) priceTag(ctx, fmtPrice(last.close, s.instrTick), y, L.axisX, last.close >= last.open ? "#15803d" : "#b91c1c"); }

  // badges first (right-aligned), then the legend in the space that is left
  ctx.font = `bold 10px ${T.sans}`;
  const badgeW = s.badges.reduce((a, b) => a + ctx.measureText(b.text).width + 18, 0);
  const legendBar = hoverBar !== null ? bars[hoverBar] : bars[Math.min(bars.length - 1, i1)];
  drawLegend(ctx, legendBar, s.head, s.instrTick, 10, 16, L.axisX - 8 - badgeW);
  let bx = L.axisX - 8;
  ctx.font = `bold 10px ${T.sans}`; ctx.textAlign = "right"; ctx.textBaseline = "middle";
  for (const b of s.badges) { const w = ctx.measureText(b.text).width + 12; ctx.fillStyle = rgba(b.color, 0.18); ctx.fillRect(bx - w, 6, w, 18); ctx.strokeStyle = rgba(b.color, 0.7); ctx.strokeRect(bx - w + 0.5, 6.5, w - 1, 17); ctx.fillStyle = b.color; ctx.fillText(b.text, bx - 6, 15.5); bx -= w + 6; }

  // crosshair + hover tooltip
  if (s.hover && hoverBar !== null) {
    const hb = bars[hoverBar]!;
    const inMain = s.hover.y >= L.main.y && s.hover.y <= L.main.y + L.main.h;
    drawCrosshair(ctx, L, idxToX(vp, L.main, hoverBar), s.hover.y, inMain ? fmtPrice(yToPrice(vp, L.main, s.hover.y), s.instrTick) : null, `${fmtDay(Date.parse(hb.ts_open))} ${fmtClock(Date.parse(hb.ts_open))}`);
    if (hoverCell) {
      const text = `${fmtPrice(hoverCell.price, bars[hoverCell.barIdx]!.tick)}   Sell ${fmtVol(hoverCell.bid)}   Buy ${fmtVol(hoverCell.ask)}   Δ ${fmtSigned(hoverCell.ask - hoverCell.bid)}`;
      ctx.font = `11px ${T.mono}`; const w = ctx.measureText(text).width + 16;
      const tx = Math.min(s.hover.x + 14, L.axisX - w - 4), ty = Math.max(30, s.hover.y - 30);
      ctx.fillStyle = "rgba(15,23,42,0.96)"; ctx.fillRect(tx, ty, w, 22); ctx.strokeStyle = "#475569"; ctx.strokeRect(tx + 0.5, ty + 0.5, w - 1, 21);
      ctx.fillStyle = T.textBright; ctx.textAlign = "left"; ctx.textBaseline = "middle"; ctx.fillText(text, tx + 8, ty + 11.5);
    }
  }
  if (s.message) { ctx.fillStyle = T.text; ctx.font = `14px ${T.sans}`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(s.message, L.main.w / 2, L.main.h / 2); }
  return { layout: L, vp, hoverBar, hoverCell, rangeFromData };
}

export type { PlotRect };
