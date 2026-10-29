import { useEffect, useState } from "react";
import { fetchHeatmap, fetchObservations } from "../lib/net";
import type { ObservationDTO } from "../lib/types";
import { HeatmapCanvas } from "./Panels";
import { ScenarioPanel } from "./ScenarioPanel";
import type { PaneContext } from "./Workspace";

const h4: React.CSSProperties = { margin: "18px 0 6px", fontSize: 14 };
const muted: React.CSSProperties = { fontSize: 12, color: "#9ca3af", fontWeight: 400 };

/** Descriptive context for the first pane: observations, scenario rules and (when the provider has depth) a liquidity heatmap. */
export function Insights({ ctx }: { ctx: PaneContext | null }) {
  const [obs, setObs] = useState<ObservationDTO[]>([]);
  const [heat, setHeat] = useState<number[][]>([]);
  useEffect(() => {
    if (!ctx) return;
    let stale = false;
    const base = { iid: ctx.iid, tick: ctx.tick, start: ctx.start, end: ctx.end, tf: ctx.tf, session: ctx.session };
    fetchObservations(base).then((o) => !stale && setObs(o.observations)).catch(() => !stale && setObs([]));
    // heatmap: first 30 minutes of the window's last session day, where depth exists
    const lastDay = new Date(Date.parse(ctx.end) - 24 * 3600 * 1000);
    const s = new Date(Date.UTC(lastDay.getUTCFullYear(), lastDay.getUTCMonth(), lastDay.getUTCDate(), 3, 45));
    fetchHeatmap({ iid: ctx.iid, tick: ctx.tick, start: s.toISOString(), end: new Date(s.getTime() + 30 * 60000).toISOString(), dt: 5 })
      .then((h) => !stale && setHeat(h.intensity)).catch(() => !stale && setHeat([]));
    return () => { stale = true; };
  }, [ctx?.iid, ctx?.tick, ctx?.tf, ctx?.start, ctx?.end, ctx?.session]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ctx) return null;
  return (
    <section style={{ padding: "0 16px 32px", maxWidth: 1200 }}>
      <h4 style={h4}>Observations <span style={muted}>(descriptive context for the first pane, never instructions)</span></h4>
      {obs.length === 0 ? <p style={muted}>None in this window.</p> : (
        <ul style={{ fontSize: 13, lineHeight: 1.55, paddingLeft: 18 }}>
          {obs.slice(0, 14).map((o, i) => <li key={i}>{o.summary} <em style={muted}>[{o.data_quality}, confidence {o.confidence}]</em></li>)}
        </ul>
      )}
      <h4 style={h4}>Scenario rules <span style={muted}>(context only)</span></h4>
      <ScenarioPanel query={{ iid: ctx.iid, tick: ctx.tick, start: ctx.start, end: ctx.end, tf: ctx.tf }} />
      {heat.length > 0 && <>
        <h4 style={h4}>Liquidity heatmap <span style={muted}>(first 30 minutes of the latest session; resting quantity shows intent, not execution)</span></h4>
        <HeatmapCanvas intensity={heat} width={1000} height={180} />
      </>}
    </section>
  );
}
