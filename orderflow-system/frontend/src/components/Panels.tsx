import { useEffect, useRef } from "react";
import { cvdSegments, heatmapPixels } from "../lib/panels";
import type { FootprintBarDTO } from "../lib/types";

export function CvdPane({ bars, width, height }: { bars: FootprintBarDTO[]; width: number; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const ctx = ref.current?.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);
    ctx.strokeStyle = "#60a5fa"; ctx.lineWidth = 1.5;
    for (const seg of cvdSegments(bars, width, height)) {
      ctx.beginPath();
      seg.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.stroke();
    }
  }, [bars, width, height]);
  return <canvas ref={ref} width={width} height={height} aria-label="Cumulative delta, resets each session" />;
}

export function HeatmapCanvas({ intensity, width, height }: { intensity: number[][]; width: number; height: number }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !intensity.length) return;
    const { width: w, height: h, data } = heatmapPixels(intensity);
    const off = document.createElement("canvas");
    off.width = w; off.height = h;
    off.getContext("2d")!.putImageData(new ImageData(data, w, h), 0, 0);
    const ctx = canvas.getContext("2d")!;
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, 0, width, height);
  }, [intensity, width, height]);
  return <canvas ref={ref} width={width} height={height} aria-label="Resting liquidity heatmap: warmer colour means more resting quantity" />;
}
