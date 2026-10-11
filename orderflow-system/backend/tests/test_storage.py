import asyncio
import os
import pathlib
from datetime import UTC, datetime, timedelta

import pglast
import pytest

from ofx.domain import AggressorSide as S
from ofx.domain import Instrument
from ofx.orderflow import detectors
from ofx.orderflow.footprint import apply_session_cvd, build_footprint
from ofx.providers.base import Capabilities
from ofx.storage import pg
from ofx.storage.pg import PgStore, StoredTradesProvider
from tests.conftest import T0, tr

MIG = pathlib.Path(__file__).parent.parent / "migrations"


def test_all_statements_parse_as_postgres_sql():
    for sql in pg.ALL_SQL:
        parts = sql.split("%s")
        pglast.parse_sql("".join(p + (f"${i + 1}" if i < len(parts) - 1 else "") for i, p in enumerate(parts)))
    for f in sorted(MIG.glob("*.sql")):
        assert pglast.parse_sql(f.read_text())


DSN = os.environ.get("OFX_TEST_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set OFX_TEST_DSN to run against a real PostgreSQL")


@pytest.fixture()
def store():
    import psycopg
    conn = psycopg.connect(DSN)
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        cur.execute((MIG / "0001_schema.sql").read_text())
    conn.commit()
    yield PgStore(conn)
    conn.close()


@needs_db
def test_trades_roundtrip_idempotent_and_ordered(store):
    store.upsert_instrument(Instrument("SYN:TEST", "TEST", "SYN", 0.5), "synthetic")
    trades = [tr(1, 100.5, 3, S.ASK, 1), tr(2, 100.0, 2, S.BID, 2), tr(2, 100.0, 1, S.UNKNOWN, 3, "none")]
    store.insert_trades("SYN:TEST", trades)
    store.insert_trades("SYN:TEST", trades)  # replay after a reconnect must not double count
    got = store.load_trades("SYN:TEST", T0, T0 + timedelta(minutes=1))
    assert [(t.seq, t.side, t.price, t.qty) for t in got] == [(1, S.ASK, 100.5, 3.0), (2, S.BID, 100.0, 2.0), (3, S.UNKNOWN, 100.0, 1.0)]
    assert got[0].ts == trades[0].ts and got[0].ts.tzinfo is not None


@needs_db
def test_check_constraints_reject_bad_rows(store):
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation), store.conn.cursor() as cur:
        cur.execute("INSERT INTO trades VALUES ('x', now(), 1, 10, -5, 1, 'exchange')")
    store.conn.rollback()


@needs_db
def test_closed_bar_is_immutable_forming_bar_updates(store):
    bars = apply_session_cvd(build_footprint([tr(1, 100, 5, S.ASK, 1)], 1.0, timedelta(minutes=1)))
    b = bars[0]
    store.upsert_bar("X", "1m", b, closed=False)
    b2 = apply_session_cvd(build_footprint([tr(1, 100, 5, S.ASK, 1), tr(2, 100, 7, S.ASK, 2)], 1.0, timedelta(minutes=1)))[0]
    store.upsert_bar("X", "1m", b2, closed=True)  # overwrites the forming row and closes it
    b3 = apply_session_cvd(build_footprint([tr(1, 100, 99, S.ASK, 1)], 1.0, timedelta(minutes=1)))[0]
    store.upsert_bar("X", "1m", b3, closed=True)  # must be ignored
    with store.conn.cursor() as cur:
        cur.execute("SELECT volume, closed FROM footprint_bars")
        assert [(float(v), c) for v, c in cur.fetchall()] == [(12.0, True)]


@needs_db
def test_observations_and_replay_through_service(store):
    from ofx.api.service import Service
    start = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)
    from ofx.providers.synthetic import generate_trades
    store.insert_trades("SYN:TEST", generate_trades(start, 600))
    prov = StoredTradesProvider(store, Capabilities("stored", True, True, 0, True, False))
    res = asyncio.run(Service(prov).footprint("SYN:TEST", 0.5, start, start + timedelta(minutes=10), "5m"))
    assert len(res["bars"]) == 2 and res["data_quality"] == "exact"
    bars = apply_session_cvd(build_footprint(store.load_trades("SYN:TEST", start, start + timedelta(minutes=10)), 0.5, timedelta(minutes=1)))
    obs = detectors.exhaustion(bars) + detectors.imbalance_clusters(bars)
    store.insert_observations("SYN:TEST", obs)
    assert len(store.load_observations("SYN:TEST", start, start + timedelta(minutes=10))) == len(obs) > 0
