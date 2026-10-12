import csv
import io

import pytest
from fastapi.testclient import TestClient

from ofx.api.service import BadRequest, paginate
from ofx.export import COLUMNS, footprint_rows
from ofx.main import create_app

Q = "iid=SYN:TEST&tick=0.5&start=2026-01-05T04:00:00Z&end=2026-01-05T05:00:00Z"


def c():
    return TestClient(create_app(api_key=""))


def walk(path, listkey, limit):
    out, cursor, pages = [], None, 0
    while True:
        url = f"{path}?{Q}&tf=5m&limit={limit}" + (f"&cursor={cursor}" if cursor else "")
        j = c().get(url.replace("+", "%2B")).json()
        out += j[listkey]
        pages += 1
        cursor = j["next_cursor"]
        if not cursor:
            return out, pages
        assert pages < 100


def test_footprint_pages_reassemble_to_full_result():
    full = c().get(f"/api/v1/footprint?{Q}&tf=5m").json()
    assert full["next_cursor"] is None and full["total_bars"] == len(full["bars"]) == 12
    bars, pages = walk("/api/v1/footprint", "bars", 5)
    assert pages == 3 and bars == full["bars"]  # no gaps, no duplicates, identical CVD values


def test_observations_pages_reassemble():
    full = c().get(f"/api/v1/observations?{Q}&tf=5m").json()
    obs, _ = walk("/api/v1/observations", "observations", 1)
    assert obs == full["observations"]


def test_paginate_helper_edges():
    items = [{"t": f"2026-01-05T04:0{i}:00+00:00"} for i in range(5)]
    assert paginate(items, "t", None, None) == (items, None)
    page, nxt = paginate(items, "t", 2, None)
    assert len(page) == 2 and nxt == items[2]["t"]
    assert paginate(items, "t", 10, items[3]["t"]) == (items[3:], None)
    assert paginate([], "t", 3, None) == ([], None)
    # cursor in another UTC offset must compare as an instant, not as text
    assert paginate(items, "t", 10, "2026-01-05T09:33:00+05:30")[0] == items[3:]


@pytest.mark.parametrize("limit,cursor", [(0, None), (2001, None), (5, "garbage"), (5, "2026-01-05T04:00:00")])
def test_paginate_rejects_bad_input(limit, cursor):
    with pytest.raises(BadRequest):
        paginate([{"t": "2026-01-05T04:00:00+00:00"}], "t", limit, cursor)


def test_api_rejects_bad_paging():
    assert c().get(f"/api/v1/footprint?{Q}&limit=0").status_code == 422
    assert c().get(f"/api/v1/footprint?{Q}&limit=5&cursor=nope").status_code == 400


def test_csv_export_matches_rows_helper():
    r = c().get(f"/api/v1/export/footprint?{Q}&format=csv")
    assert r.status_code == 200
    got = list(csv.reader(io.StringIO(r.text)))
    assert got[0] == COLUMNS and len(got) > 10
    data = c().get(f"/api/v1/footprint?{Q}&tf=5m").json()
    assert len(got) - 1 == len(footprint_rows(data))


def test_export_rejects_unknown_format():
    assert c().get(f"/api/v1/export/footprint?{Q}&format=xlsx").status_code == 400


def test_parquet_export_roundtrip_matches_csv():
    pq = pytest.importorskip("pyarrow.parquet")
    r = c().get(f"/api/v1/export/footprint?{Q}&format=parquet")
    assert r.status_code == 200 and r.headers["content-type"] == "application/vnd.apache.parquet"
    t = pq.read_table(io.BytesIO(r.content))
    assert t.column_names == COLUMNS
    assert str(t.schema.field("ts_open").type) == "timestamp[us, tz=UTC]"
    assert str(t.schema.field("bid_vol").type) == "double" and str(t.schema.field("row").type) == "int64"
    csv_rows = list(csv.reader(io.StringIO(c().get(f"/api/v1/export/footprint?{Q}&format=csv").text)))[1:]
    assert t.num_rows == len(csv_rows)
    tbl = t.to_pydict()
    for i, row in enumerate(csv_rows):
        assert tbl["row"][i] == int(row[1]) and tbl["bid_vol"][i] == float(row[3]) and tbl["ask_vol"][i] == float(row[4])
        assert tbl["delta"][i] == tbl["ask_vol"][i] - tbl["bid_vol"][i]


def test_parquet_empty_range_still_valid():
    pq = pytest.importorskip("pyarrow.parquet")
    from ofx.export import to_parquet
    t = pq.read_table(io.BytesIO(to_parquet([])))
    assert t.num_rows == 0 and t.column_names == COLUMNS


def test_parquet_keeps_fractional_volumes():
    pq = pytest.importorskip("pyarrow.parquet")
    from ofx.export import to_parquet
    rows = [["2026-01-05T04:00:00+00:00", 7, 3.5, 0.25, 1.75, 1.5, "exact"]]
    t = pq.read_table(io.BytesIO(to_parquet(rows))).to_pydict()
    assert t["bid_vol"] == [0.25] and t["ask_vol"] == [1.75] and t["delta"] == [1.5]
