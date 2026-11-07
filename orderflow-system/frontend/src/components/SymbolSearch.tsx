import { useEffect, useRef, useState } from "react";
import { searchInstruments } from "../lib/net";
import type { InstrumentDTO } from "../lib/types";

const box: React.CSSProperties = { background: "#111827", color: "#e5e7eb", border: "1px solid #273244", borderRadius: 4, padding: "3px 6px", fontSize: 12, width: 130 };

/** Type-ahead symbol search backed by the provider (e.g. the Angel One master for any NSE/BSE/MCX name). */
export function SymbolSearch({ onPick }: { onPick: (i: InstrumentDTO) => void }) {
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<InstrumentDTO[]>([]);
  const [state, setState] = useState<"idle" | "busy" | "none" | "error">("idle");
  const [open, setOpen] = useState(false);
  const [cur, setCur] = useState(0);
  const seq = useRef(0);
  useEffect(() => setCur(0), [hits]);
  const pick = (h: InstrumentDTO) => { onPick(h); setQ(""); setOpen(false); };

  useEffect(() => {
    const text = q.trim();
    if (!text) { setHits([]); setState("idle"); return; }
    const mine = ++seq.current;
    setState("busy");
    const t = setTimeout(() => {
      searchInstruments(text)
        .then((r) => { if (mine === seq.current) { setHits(r.instruments); setState(r.instruments.length ? "idle" : "none"); } })
        .catch(() => { if (mine === seq.current) { setHits([]); setState("error"); } });
    }, 250);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <span style={{ position: "relative" }}>
      <input aria-label="Search symbol" placeholder="Search symbol…" style={box} value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(hits.length - 1, c + 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); }
          else if (e.key === "Enter" && hits[cur]) { e.preventDefault(); pick(hits[cur]!); }
          else if (e.key === "Escape") setOpen(false);
        }} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      {open && q.trim() && (
        <div role="listbox" style={{ position: "absolute", top: 26, left: 0, zIndex: 20, minWidth: 260, maxHeight: 280, overflowY: "auto", background: "#0e1420", border: "1px solid #273244", borderRadius: 4, boxShadow: "0 6px 20px rgba(0,0,0,.5)" }}>
          {state === "busy" && <div style={{ padding: 8, color: "#9aa4b2", fontSize: 12 }}>Searching…</div>}
          {state === "none" && <div style={{ padding: 8, color: "#9aa4b2", fontSize: 12 }}>No match for “{q.trim()}”</div>}
          {state === "error" && <div style={{ padding: 8, color: "#f87171", fontSize: 12 }}>Search failed</div>}
          {hits.map((h, n) => (
            <div key={h.iid} role="option" aria-selected={n === cur} onMouseDown={(e) => { e.preventDefault(); pick(h); }}
              style={{ padding: "6px 10px", cursor: "pointer", fontSize: 12, display: "flex", justifyContent: "space-between", gap: 12, borderBottom: "1px solid #141b29", background: n === cur ? "#1d2a44" : "transparent" }}>
              <span style={{ color: "#e5e7eb" }}>{h.symbol}</span><span style={{ color: "#9aa4b2" }}>{h.exchange}</span>
            </div>
          ))}
        </div>
      )}
    </span>
  );
}
