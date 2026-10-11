import { describe, expect, it } from "vitest";
import { COLOR_STOPS, colorAt, logIntensity } from "../src/lib/color";
import { barWidth, canDrawText, cellRects, compact } from "../src/lib/layout";
import { backoffMs } from "../src/lib/net";
import type { FootprintBarDTO } from "../src/lib/types";

const bar: FootprintBarDTO = {
  ts_open: "2026-01-05T04:00:00Z", ts_close: "2026-01-05T04:05:00Z", tick: 1, open: 100, high: 102, low: 100, close: 101,
  volume: 90, delta: 10, cvd_open: 0, cvd_close: 10, poc_row: 101, unknown_share: 0, quality: "exact",
  rows: { "100": [10, 5], "101": [20, 30], "102": [5, 20] },
  imbalances: [{ row: 102, side: "ask" }], stacked: [{ side: "ask", low_row: 101, high_row: 102 }],
};

describe("color", () => {
  it("matches the backend stops at the ends and midpoint", () => {
    expect(colorAt(0)).toEqual([8, 16, 48]);
    expect(colorAt(1)).toEqual([220, 50, 40]);
    expect(colorAt(0.5)).toEqual([40, 170, 160]);
    expect(COLOR_STOPS).toHaveLength(5);
  });
  it("clamps out-of-range input", () => { expect(colorAt(-3)).toEqual(colorAt(0)); expect(colorAt(9)).toEqual(colorAt(1)); });
  it("log intensity is within [0,1] and zero stays zero", () => {
    const x = logIntensity([0, 1, 10, 1000]);
    expect(x[0]).toBe(0); expect(Math.max(...x)).toBeLessThanOrEqual(1); expect(x[1]!).toBeLessThan(x[2]!);
  });
});

describe("layout", () => {
  const g = { x: 10, width: 60, priceToY: (p: number) => 500 - p * 4 };
  it("builds one rect per row with POC and imbalance flags", () => {
    const rects = cellRects(bar, g)!;
    expect(rects).toHaveLength(3);
    expect(rects.find((r) => r.row === 101)!.isPoc).toBe(true);
    expect(rects.find((r) => r.row === 102)!.imbalance).toBe("ask");
    expect(rects.find((r) => r.row === 100)!.stacked).toBe(false);
    expect(rects[0]!.h).toBeCloseTo(4);
  });
  it("returns null when the chart cannot map a price", () => {
    expect(cellRects(bar, { ...g, priceToY: () => null })).toBeNull();
  });
  it("hides text in cells that are too small", () => {
    expect(canDrawText({ h: 10, w: 60 })).toBe(false);
    expect(canDrawText({ h: 12, w: 60 })).toBe(true);
    expect(canDrawText({ h: 12, w: 30 })).toBe(false);
  });
  it("formats and sizes", () => {
    expect(compact(1250)).toBe("1.3k"); expect(compact(7)).toBe("7"); expect(barWidth(1)).toBe(0);
  });
});

describe("net", () => {
  it("backs off exponentially, capped, with bounded jitter", () => {
    expect(backoffMs(0, () => 0.5)).toBe(500);
    expect(backoffMs(2, () => 0.5)).toBe(2000);
    expect(backoffMs(20, () => 0.5)).toBe(15000);
    expect(backoffMs(1, () => 0)).toBe(800); expect(backoffMs(1, () => 1)).toBe(1200);
  });
});
