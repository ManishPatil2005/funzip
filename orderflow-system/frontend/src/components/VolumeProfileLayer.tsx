import { useEffect, useRef } from "react";
import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { profileBars } from "../lib/panels";

export interface VPData { rows: Record<string, number>; tick: number; levels: { poc_row: number; vah_row: number; val_row: number } }

/** Right-anchored horizontal volume profile painted over the chart; POC and the value area are highlighted. */
export function VolumeProfileLayer({ chart, series, data, width, height, maxWidth = 140 }: { chart: IChartApi; series: ISeriesApi<"Candlestick">; data: VPData | null; width: number; height: number; maxWidth?: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !data) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = width * dpr; canvas.height = height * dpr;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    const draw = () => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, width, height);
      for (const b of profileBars(data.rows, data.levels, data.tick, (p) => series.priceToCoordinate(p), maxWidth)) {
        ctx.fillStyle = b.isPoc ? "rgba(250,204,21,0.8)" : b.inValueArea ? "rgba(96,165,250,0.55)" : "rgba(148,163,184,0.35)";
        ctx.fillRect(width - 60 - b.w, b.y, b.w, Math.max(1, b.h - 1));
      }
    };
    const schedule = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(draw); };
    chart.timeScale().subscribeVisibleLogicalRangeChange(schedule);
    schedule();
    return () => { cancelAnimationFrame(raf); chart.timeScale().unsubscribeVisibleLogicalRangeChange(schedule); };
  }, [chart, series, data, width, height, maxWidth]);
  return <canvas ref={ref} style={{ position: "absolute", inset: 0, width, height, pointerEvents: "none", zIndex: 2 }} />;
}
