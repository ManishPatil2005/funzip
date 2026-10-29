import { describe, expect, it } from "vitest";
import { layoutPanes, MIN_MAIN_H, AXIS_W, TIME_H } from "../src/render/layout";

describe("pane layout", () => {
  it("stacks main, stats, delta and time axis without gaps or overlap", () => {
    const L = layoutPanes(1400, 900, { stats: true, delta: true });
    expect(L.main.y).toBe(0);
    expect(L.stats!.y).toBe(L.main.h);
    expect(L.delta!.y).toBe(L.stats!.y + L.stats!.h);
    expect(L.time.y).toBe(L.delta!.y + L.delta!.h);
    expect(L.time.y + TIME_H).toBe(900);
    expect(L.axisX).toBe(1400 - AXIS_W);
  });
  it("sheds the delta pane first, then the stats table, to keep the main chart readable", () => {
    const mid = layoutPanes(900, 420, { stats: true, delta: true });
    expect(mid.delta).toBeNull(); expect(mid.stats).not.toBeNull(); expect(mid.main.h).toBeGreaterThanOrEqual(MIN_MAIN_H);
    const small = layoutPanes(900, 260, { stats: true, delta: true });
    expect(small.delta).toBeNull(); expect(small.stats).toBeNull(); expect(small.main.h).toBe(260 - TIME_H);
  });
  it("respects toggles", () => {
    const L = layoutPanes(1400, 900, { stats: false, delta: false });
    expect(L.stats).toBeNull(); expect(L.delta).toBeNull(); expect(L.main.h).toBe(900 - TIME_H);
  });
});
