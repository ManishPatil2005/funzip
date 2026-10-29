import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fmtPrice } from "../lib/format";
import { connectWS, fetchFootprint, fetchSessionProfiles, fetchTPO } from "../lib/net";
import { defaultDays, lastWeekdays } from "../lib/range";
import { pickRowSize, rowLadder } from "../lib/scale";
import type { FootprintBarDTO, InstrumentDTO, SessionProfileDTO, TPODTO } from "../lib/types";
import { MIN_SPACING, panX, panY, zoomX, zoomY, type Viewport } from "../lib/viewport";
import { renderScene, type Mode, type SceneOpts, type SceneResult } from "../render/scene";
import { T } from "../render/theme";

export interface PaneConfig { iid: string; tf: string; mode: Mode }
export interface PaneContext { iid: string; tick: number; tf: string; start: string; end: string; session: string }
interface Props { instruments: InstrumentDTO[]; initial: PaneConfig; onContext?: (c: PaneContext) => void }

const TFS = ["1m", "5m", "15m", "30m", "1h"];
const MIN_ROW_PX: Record<Mode, number> = { footprint: 16, candles: 7, tpo: 13 };
const DEFAULT_OPTS: SceneOpts = { stats: true, delta: true, vwap: true, profile: true, imbalance: true, volume: true };

const btn = (on: boolean): React.CSSProperties => ({
  background: on ? "#1d4ed8" : "#111827", color: on ? "#fff" : "#cbd5e1", border: `1px solid ${on ? "#3b82f6" : "#273244"}`,
  borderRadius: 4, padding: "2px 7px", fontSize: 11.5, cursor: "pointer", fontFamily: T.sans,
});
const sel: React.CSSProperties = { background: "#111827", color: "#e5e7eb", border: "1px solid #273244", borderRadius: 4, padding: "3px 6px", fontSize: 12 };

/** One chart pane: toolbar + canvas engine. Everything the user can change lives here so panes are independent. */
export function Workspace({ instruments, initial, onContext }: Props) {
  const [iid, setIid] = useState(initial.iid);
  const [tf, setTf] = useState(initial.tf);
  const [mode, setMode] = useState<Mode>(initial.mode);
  const [days, setDays] = useState(defaultDays(initial.tf));
  const [rowMode, setRowMode] = useState<"auto" | number>("auto");
  const [ratio, setRatio] = useState(3);
  const [opts, setOpts] = useState<SceneOpts>(DEFAULT_OPTS);
  const inst = instruments.find((i) => i.iid === iid) ?? instruments[0];
  const [autoTick, setAutoTick] = useState<number>(inst?.row_hint ?? 1);
  const resolvedTick = rowMode === "auto" ? autoTick : rowMode;

  const [bars, setBars] = useState<FootprintBarDTO[]>([]);
  const [barsKey, setBarsKey] = useState(""); // which (instrument|timeframe|days) the current bars belong to
  const [provider, setProvider] = useState(""); const [quality, setQuality] = useState("");
  const [sess, setSess] = useState<SessionProfileDTO[]>([]);
  const [tpo, setTpo] = useState<TPODTO[]>([]);
  const [loading, setLoading] = useState(true); const [err, setErr] = useState(""); const [live, setLive] = useState(false);
  const [profBusy, setProfBusy] = useState(false);
  const [size, setSize] = useState({ w: 800, h: 520 });

  const wrap = useRef<HTMLDivElement>(null), canvas = useRef<HTMLCanvasElement>(null);
  const vpRef = useRef<Viewport>({ spacing: 80, rightIdx: 0, lo: 0, hi: 1, autoY: true });
  const hover = useRef<{ x: number; y: number } | null>(null);
  const result = useRef<SceneResult | null>(null);
  const raf = useRef(0), rowTimer = useRef<ReturnType<typeof setTimeout>>();
  const viewKey = useRef("");

  const range = useMemo(() => lastWeekdays(days), [days]);
  const tsMs = useMemo(() => bars.map((b) => Date.parse(b.ts_open)), [bars]);
  const session = inst?.session ?? "";

  // --- data
  useEffect(() => {
    if (!inst) return;
    let stale = false;
    setLoading(true); setErr("");
    fetchFootprint({ iid, tick: resolvedTick, start: range.start, end: range.end, tf, ratio, session })
      .then((f) => { if (!stale) { setBars(f.bars); setBarsKey(`${iid}|${tf}|${days}`); setProvider(f.provider); setQuality(f.data_quality); } })
      .catch((e: Error) => { if (!stale) { setErr(e.message); setBars([]); } })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [iid, tf, days, range.start, range.end, resolvedTick, ratio, session, inst]);

  useEffect(() => {
    if (!inst) return;
    let stale = false;
    const q = { iid, tick: resolvedTick, start: range.start, end: range.end, session: session || "CRYPTO" };
    const done = () => { if (!stale) setProfBusy(false); };
    if (mode === "candles" && opts.profile) { setProfBusy(true); fetchSessionProfiles(q).then((r) => !stale && setSess(r.sessions)).catch(() => !stale && setSess([])).finally(done); }
    if (mode === "tpo") { setProfBusy(true); fetchTPO({ ...q, period: 30 }).then((r) => !stale && setTpo(r.profiles)).catch(() => !stale && setTpo([])).finally(done); }
    return () => { stale = true; };
  }, [iid, mode, opts.profile, resolvedTick, range.start, range.end, session, inst]);

  useEffect(() => {
    if (!inst) return;
    return connectWS(`${iid}:footprint`, (m) => {
      const msg = m as { type?: string; bar?: FootprintBarDTO };
      if (msg.type !== "footprint" || !msg.bar || Math.abs(msg.bar.tick - resolvedTick) > 1e-9) return;
      const bar = msg.bar; setLive(true);
      setBars((prev) => { const i = prev.findIndex((b) => b.ts_open === bar.ts_open); if (i < 0) return [...prev, bar].slice(-2000); const n = prev.slice(); n[i] = bar; return n; });
    }, () => setLive(false));
  }, [iid, resolvedTick, inst]);

  useEffect(() => { if (inst) onContext?.({ iid, tick: resolvedTick, tf, start: range.start, end: range.end, session }); }, [iid, resolvedTick, tf, range.start, range.end, session, inst, onContext]);

  // --- view
  const plotW = Math.max(100, size.w - 72);
  const initView = useCallback((n: number, m: Mode, keepRight = false) => {
    const perDay = Math.max(1, bars.filter((b) => b.ts_open.slice(0, 10) === bars[n - 1]?.ts_open.slice(0, 10)).length);
    // footprint: at least ~110px per bar so the bid x ask numbers fit
    const spacing = m === "footprint" ? Math.min(220, Math.max(100, plotW / Math.min(Math.max(n, 1), Math.max(4, Math.floor(plotW / 110)))))
      : m === "candles" ? Math.min(30, Math.max(MIN_SPACING, plotW / Math.min(Math.max(n, 1), 90)))
      : Math.min(80, Math.max(8, plotW / (perDay * 2.2)));
    // leave room on the right for the visible-range profile so it never sits on the latest bar
    const margin = m === "footprint" && opts.profile ? Math.min(plotW * 0.16, 150) / spacing + 0.8 : 1.5;
    vpRef.current = { ...vpRef.current, spacing, rightIdx: keepRight ? vpRef.current.rightIdx : n - 1 + margin, autoY: true };
  }, [bars, plotW, opts.profile]);

  useEffect(() => {
    // reset the view only when the bars that arrived belong to a new instrument/timeframe/range, never on a stale array
    if (bars.length && barsKey && viewKey.current !== barsKey) { viewKey.current = barsKey; initView(bars.length, mode); }
  }, [bars, barsKey, mode, initView]);
  useEffect(() => { if (bars.length) initView(bars.length, mode, true); }, [mode]); // eslint-disable-line react-hooks/exhaustive-deps

  // --- draw
  const inputs = useRef({ bars, tsMs, mode, opts, sess, tpo, inst, resolvedTick, provider, quality, live, loading, err, tf, rowMode, profBusy });
  inputs.current = { bars, tsMs, mode, opts, sess, tpo, inst, resolvedTick, provider, quality, live, loading, err, tf, rowMode, profBusy };

  const draw = useCallback(() => {
    const c = canvas.current; const I = inputs.current;
    if (!c || !I.inst) return;
    const dpr = window.devicePixelRatio || 1;
    if (c.width !== Math.round(size.w * dpr) || c.height !== Math.round(size.h * dpr)) { c.width = Math.round(size.w * dpr); c.height = Math.round(size.h * dpr); }
    const ctx = c.getContext("2d"); if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const badges: { text: string; color: string }[] = [];
    if (I.provider === "synthetic") badges.push({ text: "DEMO DATA", color: "#f59e0b" });
    if (I.quality) badges.push({ text: `DELTA ${I.quality.toUpperCase().replace("_", " ")}`, color: I.quality === "exact" ? "#22c55e" : "#f59e0b" });
    if (I.live) badges.push({ text: "LIVE", color: "#22c55e" });
    if ((I.loading || I.profBusy) && I.bars.length) badges.push({ text: "LOADING…", color: "#38bdf8" });
    const message = I.err ? `Error: ${I.err}` : I.loading && !I.bars.length ? "Loading…" : !I.bars.length ? "No trades in this window" : "";
    const maxRight = Math.max(0, I.bars.length - 1) + 12;
    if (!(vpRef.current.rightIdx <= maxRight)) vpRef.current = { ...vpRef.current, rightIdx: I.bars.length - 1 + 1.5 }; // also repairs NaN
    const res = renderScene(ctx, {
      w: size.w, h: size.h, bars: I.bars, tsMs: I.tsMs, vp: vpRef.current, mode: I.mode, opts: I.opts, sessionProfiles: I.sess, tpo: I.tpo,
      hover: hover.current, head: `${I.inst.symbol} · ${I.tf} · row ${fmtPrice(I.resolvedTick, I.inst.tick_size)}`, instrTick: I.inst.tick_size, badges, message,
    });
    result.current = res;
    // adapt the row size to what is on screen so numbers stay readable
    // only adapt once the price range is real (derived from visible bars or set by the user), never from the initial placeholder range
    if (I.rowMode === "auto" && I.bars.length && res.rangeFromData && res.vp.hi - res.vp.lo > I.inst.tick_size * 20) {
      const want = pickRowSize(I.inst.tick_size, res.vp.hi - res.vp.lo, res.layout.main.h, MIN_ROW_PX[I.mode]);
      if (Math.abs(want - I.resolvedTick) > 1e-12) { clearTimeout(rowTimer.current); rowTimer.current = setTimeout(() => setAutoTick(want), 350); }
      else clearTimeout(rowTimer.current);
    }
  }, [size.w, size.h]);

  const request = useCallback(() => { cancelAnimationFrame(raf.current); raf.current = requestAnimationFrame(draw); }, [draw]);
  useEffect(() => { request(); });
  useEffect(() => () => { cancelAnimationFrame(raf.current); clearTimeout(rowTimer.current); }, []);

  useEffect(() => {
    const el = wrap.current; if (!el) return;
    const ro = new ResizeObserver(() => setSize({ w: Math.max(300, el.clientWidth), h: Math.max(260, el.clientHeight) }));
    ro.observe(el); setSize({ w: Math.max(300, el.clientWidth), h: Math.max(260, el.clientHeight) });
    return () => ro.disconnect();
  }, []);

  // --- interaction
  useEffect(() => {
    const c = canvas.current; if (!c) return;
    let drag: { x: number; y: number; axis: boolean; movedY: number } | null = null;
    const pos = (e: MouseEvent | WheelEvent) => { const r = c.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    const L = () => result.current?.layout;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const l = L(); if (!l) return;
      const { x, y } = pos(e); const f = Math.exp(-e.deltaY * 0.0015);
      if (x > l.axisX || e.ctrlKey || e.metaKey) vpRef.current = zoomY({ ...vpRef.current, ...(result.current ? { lo: result.current.vp.lo, hi: result.current.vp.hi } : {}) }, l.main, 1 / f, Math.min(Math.max(y, l.main.y), l.main.y + l.main.h));
      else if (e.shiftKey) vpRef.current = panX(vpRef.current, e.deltaY > 0 ? -60 : 60, inputs.current.bars.length);
      else vpRef.current = zoomX(vpRef.current, l.main, f, x);
      request();
    };
    const onDown = (e: PointerEvent) => { const l = L(); if (!l) return; const { x, y } = pos(e); c.setPointerCapture(e.pointerId); drag = { x, y, axis: x > l.axisX, movedY: 0 }; };
    const onMove = (e: PointerEvent) => {
      const l = L(); const { x, y } = pos(e);
      hover.current = { x, y };
      if (drag && l) {
        const dx = x - drag.x, dy = y - drag.y; drag.x = x; drag.y = y;
        const eff = result.current?.vp ?? vpRef.current;
        if (drag.axis) vpRef.current = zoomY({ ...vpRef.current, lo: eff.lo, hi: eff.hi }, l.main, Math.exp(dy * 0.006), l.main.y + l.main.h / 2);
        else {
          vpRef.current = panX(vpRef.current, dx, inputs.current.bars.length);
          drag.movedY += dy;
          if (Math.abs(drag.movedY) > 6 || !vpRef.current.autoY) vpRef.current = panY({ ...vpRef.current, lo: eff.lo, hi: eff.hi }, l.main, dy);
        }
      }
      c.style.cursor = l && x > l.axisX ? "ns-resize" : drag ? "grabbing" : "crosshair";
      request();
    };
    const onUp = (e: PointerEvent) => { drag = null; try { c.releasePointerCapture(e.pointerId); } catch { /* not captured */ } };
    const onLeave = () => { hover.current = null; request(); };
    const onDbl = (e: MouseEvent) => {
      const l = L(); const { x } = pos(e);
      if (l && x > l.axisX) vpRef.current = { ...vpRef.current, autoY: true };
      else initView(inputs.current.bars.length, inputs.current.mode);
      request();
    };
    c.addEventListener("wheel", onWheel, { passive: false });
    c.addEventListener("pointerdown", onDown); c.addEventListener("pointermove", onMove); c.addEventListener("pointerup", onUp);
    c.addEventListener("pointerleave", onLeave); c.addEventListener("dblclick", onDbl);
    return () => { c.removeEventListener("wheel", onWheel); c.removeEventListener("pointerdown", onDown); c.removeEventListener("pointermove", onMove); c.removeEventListener("pointerup", onUp); c.removeEventListener("pointerleave", onLeave); c.removeEventListener("dblclick", onDbl); };
  }, [request, initView]);

  const compact = size.w < 780;
  const toggle = (k: keyof SceneOpts) => setOpts((o) => ({ ...o, [k]: !o[k] }));
  const ladder = useMemo(() => (inst ? rowLadder(inst.tick_size).filter((v) => v <= inst.tick_size * 2000).slice(0, 24) : []), [inst]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", minHeight: 0, background: T.bg, border: "1px solid #1c2536", borderRadius: 6, overflow: "hidden" }}>
      <div role="toolbar" aria-label="Chart controls" style={{ display: "flex", flexWrap: "wrap", gap: 4, padding: "4px 6px", alignItems: "center", borderBottom: "1px solid #1c2536", background: "#0e1420" }}>
        <select aria-label="Instrument" style={sel} value={iid} onChange={(e) => { setIid(e.target.value); const n = instruments.find((i) => i.iid === e.target.value); if (n) setAutoTick(n.row_hint); }}>
          {instruments.map((i) => <option key={i.iid} value={i.iid}>{i.symbol} ({i.exchange})</option>)}
        </select>
        {TFS.map((t) => <button key={t} style={btn(tf === t)} aria-pressed={tf === t} onClick={() => { setTf(t); setDays(defaultDays(t)); }}>{t}</button>)}
        <span style={{ width: 1, height: 18, background: "#273244" }} />
        {([["footprint", "Footprint", "FP"], ["candles", "Candles + VP", "Candles"], ["tpo", "TPO", "TPO"]] as [Mode, string, string][]).map(([m, label, short]) => <button key={m} style={btn(mode === m)} aria-pressed={mode === m} title={label} onClick={() => setMode(m)}>{compact ? short : label}</button>)}
        <span style={{ width: 1, height: 18, background: "#273244" }} />
        {[1, 3, 5].map((d) => <button key={d} style={btn(days === d)} aria-pressed={days === d} onClick={() => setDays(d)}>{d}D</button>)}
        <label style={{ color: "#9aa4b2", fontSize: 12 }}>Row <select aria-label="Row size" style={sel} value={rowMode === "auto" ? "auto" : String(rowMode)} onChange={(e) => setRowMode(e.target.value === "auto" ? "auto" : Number(e.target.value))}>
          <option value="auto">Auto ({fmtPrice(autoTick, inst?.tick_size ?? 1)})</option>
          {ladder.map((v) => <option key={v} value={v}>{fmtPrice(v, inst?.tick_size ?? 1)}</option>)}
        </select></label>
        {mode === "footprint" && !compact && <label style={{ color: "#9aa4b2", fontSize: 12 }}>Imbalance <select aria-label="Imbalance ratio" style={sel} value={ratio} onChange={(e) => setRatio(Number(e.target.value))}>{[2, 3, 4, 5].map((r) => <option key={r} value={r}>{r}×</option>)}</select></label>}
        <span style={{ width: 1, height: 18, background: "#273244" }} />
        {([["stats", "Stats", "Stats"], ["delta", "Delta bars", "Δ bars"], ["vwap", "VWAP", "VWAP"], ["profile", "Profile", "VP"], ["imbalance", "Imbalance", "Imb"], ["volume", "Volume", "Vol"]] as [keyof SceneOpts, string, string][]).map(([k, label, short]) => <button key={k} style={btn(opts[k])} aria-pressed={opts[k]} title={label} onClick={() => toggle(k)}>{compact ? short : label}</button>)}
        <button style={btn(false)} onClick={() => { initView(bars.length, mode); request(); }} title="Double-click the chart also resets">Reset</button>
      </div>
      <div ref={wrap} style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <canvas ref={canvas} aria-label={`${inst?.symbol ?? ""} order flow chart`} style={{ position: "absolute", inset: 0, width: size.w, height: size.h, cursor: "crosshair", touchAction: "none" }} />
      </div>
    </div>
  );
}
