export const T = {
  bg: "#0b0f17", panel: "#0e1420", grid: "#141b29", gridStrong: "#1c2536", text: "#9aa4b2", textBright: "#e5e7eb",
  up: "#22c55e", dn: "#ef4444", amber: "#f59e0b", imb: "#fb923c", poc: "#facc15", vwap: "#e879f9", accent: "#38bdf8",
  mono: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace", sans: "system-ui, -apple-system, Segoe UI, sans-serif",
} as const;

export const rgba = (hex: string, a: number): string => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
};

/** One distinct hue per TPO period letter; letters repeat after 26 like the backend's A-Z a-z. */
export const periodColor = (idx: number): string => `hsl(${(idx * 47) % 360} 55% ${idx < 2 ? 42 : 34}%)`;
