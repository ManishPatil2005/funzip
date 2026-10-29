/** 12345 -> "12.3K", 1.2e6 -> "1.20M". Sub-1000 values keep up to one decimal only when fractional. */
export function fmtVol(n: number): string {
  const a = Math.abs(n);
  if (a >= 1e9) return `${(n / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (a >= 1e4) return `${(n / 1e3).toFixed(1)}K`;
  if (a >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return Number.isInteger(n) ? String(n) : n.toFixed(a < 10 ? 2 : 1);
}

export const fmtSigned = (n: number): string => (n > 0 ? "+" : "") + fmtVol(n);

/** Decimals needed to show a tick size exactly (0.05 -> 2, 0.5 -> 1, 1 -> 0). */
export function decimalsFor(tick: number): number {
  for (let d = 0; d <= 8; d++) if (Math.abs(tick * 10 ** d - Math.round(tick * 10 ** d)) < 1e-9) return d;
  return 8;
}

export const fmtPrice = (p: number, tick: number): string =>
  p.toLocaleString("en-IN", { minimumFractionDigits: decimalsFor(tick), maximumFractionDigits: decimalsFor(tick) });

export const fmtPct = (x: number): string => `${(x * 100).toFixed(2)}%`;

const IST = { timeZone: "Asia/Kolkata", hour12: false } as const;

/** "09:15" in exchange time (IST). */
export function fmtClock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-GB", { ...IST, hour: "2-digit", minute: "2-digit" });
}

/** "Mon 05 Oct" in exchange time. */
export function fmtDay(ms: number): string {
  return new Date(ms).toLocaleDateString("en-GB", { timeZone: "Asia/Kolkata", weekday: "short", day: "2-digit", month: "short" });
}

/** Calendar day key in IST, for detecting session boundaries on the bar axis. */
export const dayKey = (ms: number): string => new Date(ms).toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
