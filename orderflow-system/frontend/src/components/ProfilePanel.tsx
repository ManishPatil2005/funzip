import { useEffect, useState } from "react";
import { getJSON } from "../lib/net";
import { tpoLines, type TpoProfileDTO } from "../lib/panels";

interface Props { iid: string; tick: number; start: string; end: string; session: "NSE" | "MCX" | "CRYPTO" }

/** Market Profile (TPO) text view. TPO needs only price and time, so it is exact on any feed. */
export function ProfilePanel({ iid, tick, start, end, session }: Props) {
  const [prof, setProf] = useState<TpoProfileDTO | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJSON<{ profiles: TpoProfileDTO[] }>("/api/v1/market-profile", { iid, tick, start, end, session })
      .then((r) => setProf(r.profiles.at(-1) ?? null))
      .catch((e: Error) => setErr(e.message));
  }, [iid, tick, start, end, session]);
  if (err) return <p style={{ color: "#f87171" }}>{err}</p>;
  if (!prof) return <p>No profile for this window.</p>;
  return (
    <pre style={{ fontFamily: "ui-monospace, monospace", fontSize: 12, lineHeight: 1.25, margin: 0, maxHeight: 360, overflowY: "auto" }}>
      {tpoLines(prof, tick).map((l) => `${l.price.toFixed(2).padStart(9)}  ${l.letters.padEnd(14)} ${l.tags.join(" ")}`).join("\n")}
    </pre>
  );
}
