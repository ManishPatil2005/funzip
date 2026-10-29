import { describe, expect, it } from "vitest";
import cases from "./fixtures/value_area.json";
import { decimalsFor, fmtPrice, fmtSigned, fmtVol } from "../src/lib/format";
import { pickRowSize, niceTicks, rowLadder } from "../src/lib/scale";
import { pocIndex, profileFromBars, valueAreaIndices } from "../src/lib/profile";
import { autoRange, barAt, idxToX, panX, priceToY, xToIdx, yToPrice, zoomX, zoomY, type PlotRect, type Viewport } from "../src/lib/viewport";
import { deltaCandle, intensity } from "../src/lib/stats";
import type { FootprintBarDTO } from "../src/lib/types";

const bar = (o: Partial<FootprintBarDTO>): FootprintBarDTO => ({
  ts_open: "2026-10-05T03:45:00+00:00", ts_close: "2026-10-05T04:00:00+00:00", tick: 1, open: 10, high: 12, low: 10, close: 11,
  volume: 30, delta: 6, delta_min: -2, delta_max: 8, cvd_open: 100, cvd_close: 106, bid_volume: 12, ask_volume: 18, vwap: 11,
  poc_row: 11, unknown_share: 0, quality: "exact", rows: { "10": [5, 5], "11": [3, 9], "12": [4, 4] }, imbalances: [], stacked: [], ...o,
});

describe("value area parity with the Python backend", () => {
  it("matches poc_index and value_area_indices on every fixture", () => {
    expect(cases.length).toBeGreaterThan(60);
    for (const c of cases) {
      const p = pocIndex(c.values);
      expect(p).toBe(c.poc);
      expect(valueAreaIndices(c.values, p)).toEqual([c.lo, c.hi]);
    }
  });
});

describe("formatting", () => {
  it("compacts volumes and signs deltas", () => {
    expect(fmtVol(999)).toBe("999");
    expect(fmtVol(1234)).toBe("1.23K");
    expect(fmtVol(37500)).toBe("37.5K");
    expect(fmtVol(2_340_000)).toBe("2.34M");
    expect(fmtVol(0.25)).toBe("0.25");
    expect(fmtSigned(-1060)).toBe("-1.06K");
    expect(fmtSigned(12)).toBe("+12");
  });
  it("derives price decimals from the tick", () => {
    expect([decimalsFor(0.05), decimalsFor(0.5), decimalsFor(1), decimalsFor(0.0001)]).toEqual([2, 1, 0, 4]);
    expect(fmtPrice(22625, 0.05)).toBe("22,625.00");
  });
});

describe("row size ladder (what makes numbers readable)", () => {
  it("only offers exact multiples of the tick", () => {
    for (const v of rowLadder(0.05)) expect(Math.abs(v / 0.05 - Math.round(v / 0.05))).toBeLessThan(1e-9);
    expect(rowLadder(0.05).slice(0, 5)).toEqual([0.05, 0.1, 0.2, 0.25, 0.5]);
    expect(rowLadder(1).slice(0, 4)).toEqual([1, 2, 5, 10]);
  });
  it("merges rows until each is at least minRowPx tall", () => {
    const rs = pickRowSize(0.05, 120, 600, 15); // 120 pts over 600px: need >= 3 pts per row
    expect(rs).toBe(5);
    expect((rs / 120) * 600).toBeGreaterThanOrEqual(15);
    expect(pickRowSize(0.05, 6, 600, 15)).toBe(0.2); // zoomed in: finer rows (needs >= 0.15)
  });
  it("never returns less than the tick and tolerates degenerate input", () => {
    expect(pickRowSize(0.5, 0, 600)).toBe(0.5);
    expect(pickRowSize(1, 1e9, 600)).toBeGreaterThanOrEqual(1);
  });
  it("niceTicks stays inside the range with round steps", () => {
    const t = niceTicks(22512, 22793, 6);
    expect(t[0]).toBeGreaterThanOrEqual(22512);
    expect(t.at(-1)!).toBeLessThanOrEqual(22793);
    expect(new Set(t.slice(1).map((v, i) => Math.round((v - t[i]!) * 1e6))).size).toBe(1);
  });
});

describe("viewport maths", () => {
  const r: PlotRect = { x: 0, y: 0, w: 1000, h: 500 };
  const v: Viewport = { spacing: 50, rightIdx: 40, lo: 100, hi: 200, autoY: true };
  it("maps index/x and price/y as inverses", () => {
    expect(xToIdx(v, r, idxToX(v, r, 33.5))).toBeCloseTo(33.5, 9);
    expect(yToPrice(v, r, priceToY(v, r, 137.25))).toBeCloseTo(137.25, 9);
    expect(priceToY(v, r, 200)).toBe(0);
    expect(priceToY(v, r, 100)).toBe(500);
  });
  it("zoomX keeps the bar under the cursor fixed and clamps spacing", () => {
    const a = zoomX(v, r, 1.5, 300);
    expect(xToIdx(a, r, 300)).toBeCloseTo(xToIdx(v, r, 300), 9);
    expect(zoomX(v, r, 1e6, 300).spacing).toBe(400);
    expect(zoomX(v, r, 1e-6, 300).spacing).toBe(4);
  });
  it("zoomY keeps the price under the cursor fixed and leaves auto mode", () => {
    const a = zoomY(v, r, 0.5, 125);
    expect(a.autoY).toBe(false);
    expect(yToPrice(a, r, 125)).toBeCloseTo(yToPrice(v, r, 125), 9);
    expect(a.hi - a.lo).toBeCloseTo(50, 9);
  });
  it("panX is bounded by the data", () => {
    expect(panX(v, 1e9, 100).rightIdx).toBe(0);
    expect(panX(v, -1e9, 100).rightIdx).toBe(111);
  });
  it("barAt only hits bars that exist", () => {
    expect(barAt(v, r, idxToX(v, r, 10), 100)).toBe(10);
    expect(barAt(v, r, idxToX(v, r, 150), 100)).toBeNull();
  });
  it("autoRange pads the visible extremes", () => {
    const [lo, hi] = autoRange([bar({ low: 10, high: 20 }), bar({ low: 12, high: 30 })], 0, 1)!;
    expect(lo).toBeLessThan(10); expect(hi).toBeGreaterThan(30);
    expect(autoRange([], 0, 0)).toBeNull();
  });
});

describe("profile from bars", () => {
  it("sums rows across bars and finds POC/VA", () => {
    const p = profileFromBars([bar({}), bar({ rows: { "11": [10, 10], "12": [1, 1] } })], 0, 1)!;
    expect(p.total).toBe(30 + 22);
    const r11 = p.rows.find((x) => x.row === 11)!;
    expect([r11.bid, r11.ask]).toEqual([13, 19]);
    expect(p.levels!.poc).toBe(11);
    expect(p.levels!.val).toBeLessThanOrEqual(p.levels!.poc);
    expect(p.levels!.vah).toBeGreaterThanOrEqual(p.levels!.poc);
  });
  it("refuses to blend bars with different row sizes", () => {
    expect(profileFromBars([bar({}), bar({ tick: 2 })], 0, 1)).toBeNull();
  });
});

describe("stats helpers", () => {
  it("delta candle uses CVD at the edges and running-delta extremes for wicks", () => {
    expect(deltaCandle(bar({}))).toEqual({ open: 100, close: 106, high: 108, low: 98 });
  });
  it("intensity is 1 at the largest magnitude and symmetric in sign", () => {
    expect(intensity(-50, [10, -50, 20])).toBe(1);
    expect(intensity(12.5, [50])).toBeCloseTo(0.5, 9);
  });
});
