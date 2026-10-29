/** IST is UTC+05:30 with no DST, so "midnight IST" is exactly 18:30 UTC of the previous day. */
const IST_MS = 5.5 * 3600 * 1000;

const istDate = (ms: number): Date => new Date(ms + IST_MS); // read with getUTC* to get IST wall-clock fields
const istMidnightMs = (y: number, m: number, d: number): number => Date.UTC(y, m, d) - IST_MS;

/** Window covering the last `n` completed weekdays (Mon-Fri) before today in IST. Returns ISO UTC strings. */
export function lastWeekdays(n: number, nowMs: number = Date.now()): { start: string; end: string; days: string[] } {
  const t = istDate(nowMs);
  const todayMid = istMidnightMs(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate());
  const days: string[] = [];
  let cursor = todayMid;
  while (days.length < n) {
    cursor -= 24 * 3600 * 1000;
    const wd = istDate(cursor + 1).getUTCDay(); // 0 Sun .. 6 Sat, evaluated in IST
    if (wd !== 0 && wd !== 6) days.unshift(new Date(cursor + IST_MS).toISOString().slice(0, 10));
  }
  return { start: new Date(cursor).toISOString(), end: new Date(todayMid).toISOString(), days };
}

/** Default number of trading days per timeframe so bar counts stay reasonable. */
export const defaultDays = (tf: string): number => ({ "1m": 1, "5m": 3, "15m": 5, "30m": 5, "1h": 5 }[tf] ?? 3);
