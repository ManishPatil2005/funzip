import { describe, expect, it } from "vitest";
import { priorDayLevels, stepReplay, volCone } from "../src/lib/levels";
import type { FootprintBarDTO } from "../src/lib/types";

const bar = (ts: string, o: number, h: number, l: number, c: number, rows: Record<string, [number, number]>): FootprintBarDTO => ({
  ts_open: ts, ts_close: ts, tick: 1, open: o, high: h, low: l, close: c, volume: 0, delta: 0, delta_min: 0, delta_max: 0, cvd_open: 0, cvd_close: 0,
  bid_volume: 0, ask_volume: 0, vwap: null, poc_row: 0, unknown_share: 0, quality: "exact", rows, imbalances: [], stacked: [],
});

describe("priorDayLevels", () => {
  const bars = [
    bar("2026-01-05T04:00:00Z", 100, 110, 98, 105, { "100": [5, 5], "105": [50, 50], "110": [1, 1] }),
    bar("2026-01-05T05:00:00Z", 105, 108, 95, 99, { "99": [2, 2], "105": [40, 40] }),
    bar("2026-01-06T04:00:00Z", 101, 103, 100, 102, { "101": [1, 1] }),
  ];
  it("uses the previous calendar day, not today", () => {
    const l = priorDayLevels(bars)!;
    expect(l.day).toBe("2026-01-05");
    expect(l.high).toBe(110); expect(l.low).toBe(95); expect(l.close).toBe(99);
    expect(l.poc).toBe(105); expect(l.todayOpen).toBe(101);
    expect(l.val! <= l.poc! && l.poc! <= l.vah!).toBe(true);
  });
  it("is null with a single day", () => { expect(priorDayLevels(bars.slice(0, 2))).toBeNull(); });
});

describe("volCone", () => {
  const closes = Array.from({ length: 40 }, (_, i) => 100 + Math.sin(i) * 2);
  const bars = closes.map((c, i) => bar(`2026-01-05T${String(i % 24).padStart(2, "0")}:00:00Z`, c, c, c, c, {}));
  it("widens with sqrt(k) and is symmetric around the last close", () => {
    const c = volCone(bars, 8);
    expect(c).toHaveLength(8);
    const w = (p: (typeof c)[number]) => p.up1 - p.dn1;
    expect(w(c[3]!) / w(c[0]!)).toBeCloseTo(2, 6); // k=4 vs k=1
    expect(c[0]!.up2 - closes[39]!).toBeCloseTo(2 * (c[0]!.up1 - closes[39]!), 9);
    expect(c[0]!.up1 - closes[39]!).toBeCloseTo(closes[39]! - c[0]!.dn1, 9);
  });
  it("ignores returns that cross a day boundary", () => {
    const two = [
      ...Array.from({ length: 8 }, (_, i) => bar(`2026-01-05T0${i}:00:00Z`, 100, 100, 100, 100 + (i % 2), {})),
      ...Array.from({ length: 8 }, (_, i) => bar(`2026-01-06T0${i}:00:00Z`, 150, 150, 150, 150 + (i % 2), {})), // +50% gap overnight
    ];
    const c = volCone(two, 1)[0]!;
    expect(c.up1 - c.dn1).toBeLessThan(10); // would be >> 10 if the gap leaked into sigma
  });
  it("returns nothing with too little history", () => { expect(volCone(bars.slice(0, 5))).toEqual([]); });
});

describe("stepReplay", () => {
  it("clamps to [1, total]", () => {
    expect(stepReplay(5, 10)).toBe(6); expect(stepReplay(10, 10)).toBe(10); expect(stepReplay(1, 10, -1)).toBe(1);
  });
});
