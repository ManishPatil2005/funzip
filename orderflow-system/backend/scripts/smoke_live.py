"""READ-ONLY live smoke test. Run on YOUR machine (the build sandbox cannot reach these hosts).

    cd backend && pip install -r requirements.txt && python scripts/smoke_live.py [--angel-token 3045 --angel-exch NSE]

Reads backend/.env (never printed). Performs only: Angel login + one historical-candle request; Delta public
products + recent trades. No order, balance or position endpoint is called anywhere in this project.
Output is redacted: secrets, tokens and the TOTP are never echoed. Paste the output back if something fails.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import pathlib
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from ofx.providers import angel, delta  # noqa: E402


def load_env(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip("'\""))


async def angel_check(token: str, exch: str) -> None:
    print("== Angel One")
    try:
        creds = angel.credentials_from_env()
        p = angel.AngelProvider(creds, {"X:T": (exch, token)})
        await p.login()
        print("login: OK")
        end = datetime.now(UTC)
        c = await p.candles("X:T", end - timedelta(days=3), end, "5m")
        print(f"candles: {len(c)} rows; first={c[0].ts_open.isoformat() if c else None}")
    except Exception as e:  # message only; request bodies are never included
        print(f"FAILED: {type(e).__name__}: {str(e)[:200]}")


async def delta_check() -> None:
    print("== Delta Exchange (public data)")
    for base, ws in ((delta.INDIA_REST, delta.INDIA_WS), (delta.GLOBAL_REST, delta.GLOBAL_WS)):
        try:
            p = delta.DeltaProvider(base_url=base, ws_url=ws)
            ins = await p.instruments()
            print(f"{base}: products={len(ins)}")
            sym = next((i for i in ins if i.symbol == "BTCUSD"), ins[0] if ins else None)
            if sym is None:
                continue
            raw = await p._get(f"/v2/trades/{sym.symbol}")
            print(f"sample trade keys: {sorted(raw[0].keys()) if raw else 'none'}")
            has_roles = bool(raw) and "buyer_role" in raw[0] and "seller_role" in raw[0]
            print(f"taker side present in payload: {has_roles}  -> set DELTA_TAKER_VERIFIED=1 only if True")
            end = datetime.now(UTC)
            c = await p.candles(f"DELTA:{sym.symbol}", end - timedelta(hours=6), end, "5m")
            print(f"candles: {len(c)} rows")
            return
        except Exception as e:
            print(f"{base}: FAILED {type(e).__name__}: {str(e)[:160]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--angel-token", default="3045", help="Angel symbol token (default 3045 = SBIN-EQ on NSE [unverified])")
    ap.add_argument("--angel-exch", default="NSE")
    a = ap.parse_args()
    load_env(pathlib.Path(__file__).resolve().parent.parent / ".env")
    asyncio.run(angel_check(a.angel_token, a.angel_exch))
    asyncio.run(delta_check())
