// Mirrors ofx/orderflow/heatmap.py COLOR_STOPS exactly (a test pins the equality).
export const COLOR_STOPS: ReadonlyArray<readonly [number, readonly [number, number, number]]> = [
  [0.0, [8, 16, 48]], [0.25, [24, 80, 160]], [0.5, [40, 170, 160]], [0.75, [240, 200, 60]], [1.0, [220, 50, 40]],
];

export function colorAt(x: number): [number, number, number] {
  const v = Math.min(1, Math.max(0, x));
  for (let i = 0; i + 1 < COLOR_STOPS.length; i++) {
    const [a, ca] = COLOR_STOPS[i]!;
    const [b, cb] = COLOR_STOPS[i + 1]!;
    if (v <= b) {
      const f = b === a ? 0 : (v - a) / (b - a);
      return [0, 1, 2].map((k) => Math.round(ca[k]! + f * (cb[k]! - ca[k]!))) as [number, number, number];
    }
  }
  return [...COLOR_STOPS[COLOR_STOPS.length - 1]![1]] as [number, number, number];
}

export const css = (c: readonly [number, number, number]) => `rgb(${c[0]},${c[1]},${c[2]})`;

/** Log-scaled intensity clipped at a percentile, same rule as the backend `intensity(scale="log")`. */
export function logIntensity(values: number[], clipPercentile = 99): number[] {
  const pos = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (!pos.length) return values.map(() => 0);
  const k = (pos.length - 1) * (clipPercentile / 100);
  const lo = Math.floor(k), hi = Math.ceil(k);
  const cap = (pos[lo]! + (pos[hi]! - pos[lo]!) * (k - lo)) || pos[pos.length - 1]!;
  return values.map((v) => (v > 0 ? Math.min(1, Math.log1p(Math.min(v, cap)) / Math.log1p(cap)) : 0));
}
