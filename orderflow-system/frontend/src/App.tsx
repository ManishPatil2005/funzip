import { useEffect, useState } from "react";
import { Insights } from "./components/Insights";
import { Workspace, type PaneConfig, type PaneContext } from "./components/Workspace";
import { fetchInstruments } from "./lib/net";
import type { InstrumentDTO } from "./lib/types";

type Layout = "1" | "1x2" | "2x2";

const presets = (first: string, second: string): Record<Layout, PaneConfig[]> => ({
  "1": [{ iid: first, tf: "15m", mode: "footprint" }],
  "1x2": [{ iid: first, tf: "15m", mode: "footprint" }, { iid: first, tf: "30m", mode: "tpo" }],
  "2x2": [{ iid: first, tf: "15m", mode: "footprint" }, { iid: first, tf: "30m", mode: "tpo" }, { iid: first, tf: "5m", mode: "candles" }, { iid: second, tf: "15m", mode: "footprint" }],
});

const lbtn = (on: boolean): React.CSSProperties => ({ background: on ? "#1d4ed8" : "#111827", color: on ? "#fff" : "#cbd5e1", border: `1px solid ${on ? "#3b82f6" : "#273244"}`, borderRadius: 4, padding: "4px 10px", fontSize: 12, cursor: "pointer" });

export default function App() {
  const [instruments, setInstruments] = useState<InstrumentDTO[]>([]);
  const [layout, setLayout] = useState<Layout>("1");
  const [ctx, setCtx] = useState<PaneContext | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => { fetchInstruments().then((r) => setInstruments(r.instruments)).catch((e: Error) => setErr(e.message)); }, []);

  const list = instruments.filter((i) => i.iid !== "SYN:TEST");
  const ordered = list.length ? list : instruments;
  const first = ordered[0]?.iid ?? "", second = ordered[1]?.iid ?? first;
  const panes = presets(first, second)[layout];
  const cols = layout === "1" ? "1fr" : "1fr 1fr", rows = layout === "2x2" ? "1fr 1fr" : "1fr";
  const demo = instruments.some((i) => i.iid.startsWith("SYN:"));

  return (
    <div style={{ background: "#0b0f17", color: "#e5e7eb", fontFamily: "system-ui, sans-serif", minHeight: "100vh" }}>
      <header style={{ display: "flex", gap: 12, alignItems: "center", padding: "8px 16px", borderBottom: "1px solid #1c2536" }}>
        <h1 style={{ fontSize: 16, margin: 0 }}>Order Flow</h1>
        {demo && <span style={{ fontSize: 12, color: "#f59e0b" }}>Demo mode: generated sessions, not a market. Point the API at a live provider for real data.</span>}
        <span style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          {(["1", "1x2", "2x2"] as Layout[]).map((l) => <button key={l} style={lbtn(layout === l)} aria-pressed={layout === l} onClick={() => setLayout(l)}>{l === "1" ? "1 chart" : l === "1x2" ? "2 charts" : "4 charts"}</button>)}
        </span>
      </header>
      {err && <p style={{ color: "#f87171", padding: 16 }}>Could not reach the API: {err}</p>}
      {first && (
        <div key={layout} style={{ display: "grid", gridTemplateColumns: cols, gridTemplateRows: rows, gap: 6, padding: 6, height: layout === "2x2" ? "calc(100vh - 56px)" : "calc(100vh - 56px)", minHeight: 520 }}>
          {panes.map((p, i) => <div key={i} style={{ minHeight: 0, minWidth: 0 }}><Workspace instruments={instruments} initial={p} onContext={i === 0 ? setCtx : undefined} /></div>)}
        </div>
      )}
      <Insights ctx={ctx} />
    </div>
  );
}
