import { useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { colorAt, css } from "../lib/color";
import { barWidth, canDrawText, cellRects, compact } from "../lib/layout";
import type { FootprintBarDTO } from "../lib/types";

interface Props { chart: IChartApi; series: ISeriesApi<"Candlestick">; bars: FootprintBarDTO[]; width: number; height: number }

/** Canvas overlay painted on top of Lightweight Charts and re-synced on every visible-range change. */
export function FootprintLayer({ chart, series, bars, width, height }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr; canvas.height = height * dpr;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;

    const draw = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      const ts = chart.timeScale();
      const maxVol = Math.max(1, ...bars.flatMap((b) => Object.values(b.rows).map(([x, y]) => x + y)));
      for (const bar of bars) {
        const t = Math.floor(Date.parse(bar.ts_open) / 1000) as never;
        const cx = ts.timeToCoordinate(t);
        if (cx === null) continue;
        const spacing = ts.options().barSpacing;
        const w = barWidth(spacing);
        const rects = cellRects(bar, { x: cx - w / 2, width: w, priceToY: (p) => series.priceToCoordinate(p) });
        if (!rects) continue;
        for (const r of rects) {
          ctx.fillStyle = css(colorAt((r.bid + r.ask) / maxVol));
          ctx.globalAlpha = 0.55;
          ctx.fillRect(r.x, r.y, r.w, r.h);
          ctx.globalAlpha = 1;
          if (r.stacked) { ctx.strokeStyle = r.imbalance === "ask" ? "#4ade80" : "#f87171"; ctx.strokeRect(r.x + 0.5, r.y + 0.5, r.w - 1, r.h - 1); }
          if (r.isPoc) { ctx.strokeStyle = "#facc15"; ctx.lineWidth = 1.5; ctx.strokeRect(r.x, r.y, r.w, r.h); ctx.lineWidth = 1; }
          if (canDrawText(r)) {
            ctx.font = "10px ui-monospace, monospace"; ctx.fillStyle = "#e5e7eb"; ctx.textBaseline = "middle";
            ctx.textAlign = "right"; ctx.fillText(compact(r.bid), r.x + r.w / 2 - 3, r.y + r.h / 2);
            ctx.textAlign = "left"; ctx.fillText(compact(r.ask), r.x + r.w / 2 + 3, r.y + r.h / 2);
          }
        }
      }
    };
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); };
    chart.timeScale().subscribeVisibleLogicalRangeChange(schedule);
    schedule();
    return () => { cancelAnimationFrame(raf); chart.timeScale().unsubscribeVisibleLogicalRangeChange(schedule); };
  }, [chart, series, bars, width, height]);

  return <canvas ref={ref} style={{ position: "absolute", inset: 0, width, height, pointerEvents: "none" }} />;
}
