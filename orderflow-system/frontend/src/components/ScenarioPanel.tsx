import { useEffect, useState } from "react";
import { fetchExamples, postScenario } from "../lib/net";
import { precheckRule } from "../lib/panels";
import type { ScenarioMatchDTO } from "../lib/types";

interface Props { query: Record<string, string | number> }

/** Edit a scenario rule (JSON) and see where its observations coincided. Results describe context only. */
export function ScenarioPanel({ query }: Props) {
  const [text, setText] = useState("");
  const [matches, setMatches] = useState<ScenarioMatchDTO[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => { fetchExamples().then((r) => setText(JSON.stringify(r.rules[0], null, 2))).catch(() => {}); }, []);
  const run = async () => {
    const pre = precheckRule(text);
    if (!pre.ok) { setErr(pre.error); setMatches(null); return; }
    try { setErr(""); setMatches((await postScenario(query, pre.spec)).matches); }
    catch (e) { setErr((e as Error).message); setMatches(null); }
  };
  return (
    <div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={12} style={{ width: "100%", fontFamily: "ui-monospace, monospace", fontSize: 12, background: "#111827", color: "#e5e7eb" }} aria-label="Scenario rule JSON" />
      <button onClick={run}>Evaluate rule</button>
      {err && <p style={{ color: "#f87171" }}>{err}</p>}
      {matches && (matches.length === 0 ? <p>No coincidences found in this window.</p> : (
        <ul style={{ fontSize: 13 }}>
          {matches.map((m, i) => (
            <li key={i}>{m.summary} <em style={{ color: "#9ca3af" }}>[{m.data_quality}, conf {m.confidence}]</em>
              <div style={{ color: "#9ca3af" }}>{m.teaching_note} — {m.limitations}</div></li>
          ))}
        </ul>
      ))}
    </div>
  );
}
