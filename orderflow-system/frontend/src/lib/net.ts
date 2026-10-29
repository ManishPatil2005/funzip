import type { FootprintResponse, InstrumentDTO, ObservationDTO, ScenarioMatchDTO, SessionProfileDTO, TPODTO } from "./types";

const KEY = import.meta.env.VITE_API_KEY as string | undefined;
const headers = (): HeadersInit => (KEY ? { "x-api-key": KEY } : {});

export async function getJSON<T>(path: string, params: Record<string, string | number>): Promise<T> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const r = await fetch(`${path}?${qs}`, { headers: headers() });
  if (!r.ok) throw new Error(`${r.status} ${(await r.text()).slice(0, 200)}`);
  return (await r.json()) as T;
}

export const fetchFootprint = (p: Record<string, string | number>) => getJSON<FootprintResponse>("/api/v1/footprint", p);
export const fetchObservations = (p: Record<string, string | number>) =>
  getJSON<{ observations: ObservationDTO[] }>("/api/v1/observations", p);

/** Exponential backoff with a cap and +-20% jitter (jitter injected so tests are deterministic). */
export function backoffMs(attempt: number, rand: () => number = Math.random, base = 500, cap = 15000): number {
  const raw = Math.min(cap, base * 2 ** attempt);
  return Math.round(raw * (0.8 + 0.4 * rand()));
}

export function connectWS(topic: string, onMessage: (m: unknown) => void, onState: (s: "open" | "closed") => void): () => void {
  let stop = false, attempt = 0, ws: WebSocket | null = null, timer: ReturnType<typeof setTimeout>;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/v1/stream?topic=${encodeURIComponent(topic)}${KEY ? `&x_api_key=${KEY}` : ""}`);
    ws.onopen = () => { attempt = 0; onState("open"); };
    ws.onmessage = (e) => onMessage(JSON.parse(e.data as string));
    ws.onclose = () => { onState("closed"); if (!stop) timer = setTimeout(open, backoffMs(attempt++)); };
  };
  open();
  return () => { stop = true; clearTimeout(timer); ws?.close(); };
}

export const fetchHeatmap = (p: Record<string, string | number>) => getJSON<{ intensity: number[][] }>("/api/v1/heatmap", p);

export async function postScenario(params: Record<string, string | number>, spec: unknown): Promise<{ matches: ScenarioMatchDTO[]; observations_considered: number }> {
  const qs = new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)]));
  const r = await fetch(`/api/v1/scenarios?${qs}`, { method: "POST", headers: { "content-type": "application/json", ...(KEY ? { "x-api-key": KEY } : {}) }, body: JSON.stringify(spec) });
  const j = (await r.json()) as { error?: string; detail?: unknown };
  if (!r.ok) throw new Error(j.error ?? JSON.stringify(j.detail ?? j).slice(0, 200));
  return j as never;
}
export const fetchExamples = () => getJSON<{ rules: unknown[] }>("/api/v1/scenarios/examples", {});

export const fetchInstruments = () => getJSON<{ instruments: InstrumentDTO[] }>("/api/v1/instruments", {});
export const fetchSessionProfiles = (p: Record<string, string | number>) => getJSON<{ sessions: SessionProfileDTO[] }>("/api/v1/session-profiles", p);
export const fetchTPO = (p: Record<string, string | number>) => getJSON<{ profiles: TPODTO[] }>("/api/v1/market-profile", p);
