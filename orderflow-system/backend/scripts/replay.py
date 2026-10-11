"""Replay recorded trades from PostgreSQL through the detectors and print a per-day summary.

    OFX_DATABASE_URL=postgresql://... python scripts/replay.py SYN:TEST 0.5 2026-01-05 2026-01-08 [--tf 5m] [--save]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ofx.api.service import TF  # noqa: E402
from ofx.replay import replay_by_day, run_detectors  # noqa: E402
from ofx.storage.pg import PgStore  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("iid")
ap.add_argument("tick", type=float)
ap.add_argument("start")
ap.add_argument("end")
ap.add_argument("--tf", default="5m", choices=sorted(TF))
ap.add_argument("--save", action="store_true", help="store observations in the observations table")
a = ap.parse_args()
dsn = os.environ.get("OFX_DATABASE_URL")
if not dsn:
    sys.exit("set OFX_DATABASE_URL")
store = PgStore.connect(dsn)
s = datetime.fromisoformat(a.start).replace(tzinfo=UTC)
e = datetime.fromisoformat(a.end).replace(tzinfo=UTC)
trades = store.load_trades(a.iid, s, e)
tf = timedelta(seconds=TF[a.tf])
print(json.dumps(replay_by_day(trades, a.tick, tf), indent=2))
if a.save:
    _, obs = run_detectors(trades, a.tick, tf)
    store.insert_observations(a.iid, obs)
    print(f"saved {len(obs)} observations")
