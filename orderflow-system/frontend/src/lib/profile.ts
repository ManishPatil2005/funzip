import type { FootprintBarDTO } from "./types";

/** Mirrors ofx/orderflow/common.py::poc_index (ties resolve nearest the centre). */
export function pocIndex(values: number[]): number {
  const peak = Math.max(...values);
  const mid = (values.length - 1) / 2;
  let best = -1;
  values.forEach((v, i) => {
    if (v === peak && (best < 0 || Math.abs(i - mid) < Math.abs(best - mid))) best = i;
  });
  return best;
}

/** Mirrors ofx/orderflow/common.py::value_area_indices (Dalton two-row method, ties go up). */
export function valueAreaIndices(values: number[], pocI: number, pct = 0.7): [number, number] {
  const n = values.length;
  const total = values.reduce((a, b) => a + b, 0);
  let lo = pocI, hi = pocI, acc = values[pocI] ?? 0;
  const sum = (a: number, b: number) => values.slice(a, b).reduce((x, y) => x + y, 0);
  while (acc < pct * total) {
    const canUp = hi + 1 < n, canDn = lo - 1 >= 0;
    if (!canUp && !canDn) break;
    const up = (canUp ? values[hi + 1]! : 0) + (hi + 2 < n ? values[hi + 2]! : 0);
    const dn = (canDn ? values[lo - 1]! : 0) + (lo - 2 >= 0 ? values[lo - 2]! : 0);
    if (canUp && (up >= dn || !canDn)) {
      const nh = Math.min(hi + 2, n - 1);
      acc += sum(hi + 1, nh + 1); hi = nh;
    } else {
      const nl = Math.max(lo - 2, 0);
      acc += sum(nl, lo); lo = nl;
    }
  }
  return [lo, hi];
}

export interface RowVol { row: number; bid: number; ask: number }
export interface ProfileLevels { poc: number; vah: number; val: number }
export interface Profile { tick: number; rows: RowVol[]; levels: ProfileLevels | null; total: number }

/** Composite profile over a slice of bars; all bars must share a tick (they do within one fetch). */
export function profileFromBars(bars: FootprintBarDTO[], first: number, last: number): Profile | null {
  const acc = new Map<number, RowVol>();
  let tick = 0;
  for (let i = first; i <= last; i++) {
    const b = bars[i];
    if (!b) continue;
    if (tick && Math.abs(b.tick - tick) > 1e-12) return null; // mixed row sizes (mid-refetch): do not blend
    tick = b.tick;
    for (const [k, [bid, ask]] of Object.entries(b.rows)) {
      const r = Number(k);
      const e = acc.get(r) ?? { row: r, bid: 0, ask: 0 };
      e.bid += bid; e.ask += ask;
      acc.set(r, e);
    }
  }
  if (!acc.size) return null;
  const lo = Math.min(...acc.keys()), hi = Math.max(...acc.keys());
  const rows: RowVol[] = [];
  for (let r = lo; r <= hi; r++) rows.push(acc.get(r) ?? { row: r, bid: 0, ask: 0 });
  const vols = rows.map((x) => x.bid + x.ask);
  const total = vols.reduce((a, b) => a + b, 0);
  if (total <= 0) return { tick, rows, levels: null, total };
  const p = pocIndex(vols);
  const [a, b] = valueAreaIndices(vols, p);
  return { tick, rows, total, levels: { poc: (lo + p) * tick, val: (lo + a) * tick, vah: (lo + b) * tick } };
}
