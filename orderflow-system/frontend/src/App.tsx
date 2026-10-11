import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi, type ISeriesApi } from "lightweight-charts";
import { FootprintLayer } from "./components/FootprintLayer";
import { connectWS, fetchFootprint, fetchObservations } from "./lib/net";
import type { FootprintBarDTO, ObservationDTO, Quality } from "./lib/types";

const W = 1100, H = 560;

export default function App() {
  const host = useRef<HTMLDivElement>(null);
  const [chart, setChart] = useState<IChartApi | null>(null);
  const [series, setSeries] = useState<ISeriesApi<"Candlestick"> | null>(null);
  const [bars, setBars] = useState<FootprintBarDTO[]>([]);
  const [obs, setObs] = useState<ObservationDTO[]>([]);
  const [quality, setQuality] = useState<Quality>("estimated");
  const [err, setErr] = useState("");

  useEffect(() => {
    const c = createChart(host.current!, { width: W, height: H, layout: { background: { color: "#0b0f17" }, textColor: "#9ca3af" }, grid: { vertLines: { color: "#111827" }, horzLines: { color: "#111827" } } });
    setChart(c); setSeries(c.addCandlestickSeries());
    return () => c.remove();
  }, []);

  useEffect(() => {
    const q = { iid: "SYN:TEST", tick: 0.5, start: "2026-01-05T04:00:00Z", end: "2026-01-05T06:00:00Z", tf: "5m" };
    Promise.all([fetchFootprint(q), fetchObservations(q)])
      .then(([f, o]) => { setBars(f.bars); setQuality(f.data_quality); setObs(o.observations); })
      .catch((e: Error) => setErr(e.message));
  }, []);

  useEffect(() => {
    // Live updates: replace the forming bar, append when a bar closes. Closed bars are never rewritten.
    return connectWS("SYN:TEST:footprint", (m) => {
      const msg = m as { type?: string; bar?: FootprintBarDTO };
      if (msg.type !== "footprint" || !msg.bar) return;
      const bar = msg.bar;
      setBars((prev) => {
        const i = prev.findIndex((b) => b.ts_open === bar.ts_open);
        if (i < 0) return [...prev, bar].slice(-500);
        const next = prev.slice();
        next[i] = bar;
        return next;
      });
    }, () => {});
  }, []);

  useEffect(() => {
    series?.setData(bars.map((b) => ({ time: Math.floor(Date.parse(b.ts_open) / 1000) as never, open: b.open, high: b.high, low: b.low, close: b.close })));
  }, [series, bars]);

  return (
    <div style={{ color: "#e5e7eb", fontFamily: "system-ui", padding: 16 }}>
      <h3 style={{ margin: "0 0 8px" }}>Order flow <span style={{ fontSize: 12, color: "#facc15" }}>data quality: {quality}</span></h3>
      {err && <p style={{ color: "#f87171" }}>{err}</p>}
      <div style={{ position: "relative", width: W, height: H }}>
        <div ref={host} />
        {chart && series && <FootprintLayer chart={chart} series={series} bars={bars} width={W} height={H} />}
      </div>
      <h4>Observations (descriptive, not instructions)</h4>
      <ul style={{ fontSize: 13, lineHeight: 1.5 }}>
        {obs.slice(0, 12).map((o, i) => (
          <li key={i}>{o.summary} <em style={{ color: "#9ca3af" }}>[{o.data_quality}, conf {o.confidence}]</em></li>
        ))}
      </ul>
    </div>
  );
}
