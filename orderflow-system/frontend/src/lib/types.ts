export type Quality = "exact" | "estimated" | "bar_approximated";

export interface FootprintBarDTO {
  ts_open: string; ts_close: string; tick: number;
  open: number; high: number; low: number; close: number;
  volume: number; delta: number; cvd_open: number; cvd_close: number;
  poc_row: number; unknown_share: number; quality: Quality;
  rows: Record<string, [number, number]>; // row -> [bid_vol, ask_vol]
  imbalances: { row: number; side: "ask" | "bid" }[];
  stacked: { side: "ask" | "bid"; low_row: number; high_row: number }[];
}

export interface FootprintResponse { provider: string; data_quality: Quality; bars: FootprintBarDTO[] }

export interface ObservationDTO {
  kind: string; ts_start: string; ts_end: string; summary: string; data_quality: Quality;
  confidence: number; price_low: number | null; price_high: number | null;
  alternative_readings: string[]; limitations: string; method: string;
}
