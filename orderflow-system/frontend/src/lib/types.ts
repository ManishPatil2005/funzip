export type Quality = "exact" | "estimated" | "bar_approximated";

export interface FootprintBarDTO {
  ts_open: string; ts_close: string; tick: number;
  open: number; high: number; low: number; close: number;
  volume: number; delta: number; delta_min: number; delta_max: number; cvd_open: number; cvd_close: number;
  bid_volume: number; ask_volume: number; vwap: number | null;
  poc_row: number; unknown_share: number; quality: Quality;
  rows: Record<string, [number, number]>; // row -> [bid_vol, ask_vol]
  imbalances: { row: number; side: "ask" | "bid" }[];
  stacked: { side: "ask" | "bid"; low_row: number; high_row: number }[];
}

export interface FootprintResponse { provider: string; data_quality: Quality; bars: FootprintBarDTO[]; total_bars: number; next_cursor: string | null }

export interface InstrumentDTO { iid: string; symbol: string; exchange: string; tick_size: number; lot_size: number; tz: string; session: string; row_hint: number }

export interface SessionProfileDTO {
  start: string; end: string; tick: number; total: number;
  rows: Record<string, [number, number]>; // row -> [bid, ask]
  levels: { poc: number; vah: number; val: number };
  nodes: { kind: "HVN" | "LVN"; price: number; volume: number }[];
}

export interface TPODTO {
  start: string; tick: number; period_minutes: number; n_periods: number; open: number | null; close: number | null;
  ib_high_row: number | null; ib_low_row: number | null;
  counts: Record<string, number>; letters: Record<string, string>;
  levels: { poc: number; vah: number; val: number; ib_high: number | null; ib_low: number | null; high: number; low: number;
            single_print_ranges: [number, number][] };
}

export interface ObservationDTO {
  kind: string; ts_start: string; ts_end: string; summary: string; data_quality: Quality;
  confidence: number; price_low: number | null; price_high: number | null;
  alternative_readings: string[]; limitations: string; method: string;
}

export interface ScenarioMatchDTO {
  rule: string; ts_start: string; ts_end: string; summary: string; teaching_note: string;
  confidence: number; data_quality: Quality; limitations: string; evidence: { kind: string; ts_end: string; confidence: number }[];
}
