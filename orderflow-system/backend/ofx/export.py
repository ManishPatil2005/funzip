"""Tabular export of footprint data (CSV rows shared with Parquet)."""
from __future__ import annotations

import io
from typing import Any

COLUMNS = ["ts_open", "row", "price", "bid_vol", "ask_vol", "delta", "bar_quality"]


class ParquetUnavailable(RuntimeError):
    pass


def footprint_rows(data: dict[str, Any]) -> list[list[Any]]:
    """One line per (bar, price row). Volumes are floats (fractional sizes are valid); unknown-side volume is not in rows by design."""
    out: list[list[Any]] = []
    for b in data["bars"]:
        for r, (bid, ask) in b["rows"].items():
            out.append([b["ts_open"], int(r), round(int(r) * b["tick"], 10), bid, ask, ask - bid, b["quality"]])
    return out


def to_parquet(rows: list[list[Any]]) -> bytes:
    """Parquet bytes with typed columns (timestamp[us, UTC], int64 row, float64 price and volumes, string quality). pyarrow is an optional extra."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as e:  # pragma: no cover - exercised only without the extra
        raise ParquetUnavailable("install the 'parquet' extra (pip install pyarrow) to export Parquet") from e
    from datetime import datetime

    cols = list(zip(*rows, strict=True)) if rows else [()] * len(COLUMNS)
    table = pa.table({
        "ts_open": pa.array([datetime.fromisoformat(t) for t in cols[0]], type=pa.timestamp("us", tz="UTC")),
        "row": pa.array(cols[1], type=pa.int64()),
        "price": pa.array(cols[2], type=pa.float64()),
        "bid_vol": pa.array(cols[3], type=pa.float64()),
        "ask_vol": pa.array(cols[4], type=pa.float64()),
        "delta": pa.array(cols[5], type=pa.float64()),
        "bar_quality": pa.array(cols[6], type=pa.string()),
    })
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()
