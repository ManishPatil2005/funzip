"""Choose the market-data provider from the environment (default: the generated demo market).

    OFX_PROVIDER=synthetic | delta | angel
    delta: public data only; optional DELTA_BASE_URL / DELTA_WS_URL / DELTA_TAKER_VERIFIED
    angel: needs ANGEL_* credentials and ANGEL_TOKENS="NSE:SBIN-EQ=NSE:3045,NSE:RELIANCE-EQ=NSE:2885"
           (iid=EXCHANGE:symboltoken; the token is Angel's numeric instrument token)
Values are read from the process environment; backend/.env is loaded first if it exists (never printed, never committed).
"""
from __future__ import annotations

import os
import pathlib
from collections.abc import Mapping
from typing import cast

from ofx.providers.base import MarketDataProvider


def load_env_file(path: pathlib.Path, env: dict[str, str] | None = None) -> None:
    target = os.environ if env is None else env
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            target.setdefault(k.strip(), v.strip().strip("'\""))


def parse_angel_tokens(raw: str) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for part in (p.strip() for p in raw.split(",") if p.strip()):
        iid, _, rest = part.partition("=")
        exch, _, tok = rest.partition(":")
        if not (iid and exch and tok):
            raise ValueError(f"ANGEL_TOKENS entry must look like NSE:SBIN-EQ=NSE:3045, got {part!r}")
        out[iid.strip()] = (exch.strip(), tok.strip())
    return out


def provider_from_env(env: Mapping[str, str] | None = None) -> MarketDataProvider | None:
    """None means "use the default synthetic provider"."""
    e = os.environ if env is None else env
    name = e.get("OFX_PROVIDER", "synthetic").lower()
    if name in ("", "synthetic"):
        return None
    if name == "delta":
        from ofx.providers.delta import DeltaProvider
        return DeltaProvider(e.get("DELTA_EXCHANGE_API_KEY", ""), e.get("DELTA_EXCHANGE_SECRET", ""))
    if name == "angel":
        from ofx.providers.angel import AngelProvider, credentials_from_env
        tokens = parse_angel_tokens(e.get("ANGEL_TOKENS", ""))
        if not tokens:
            raise ValueError("OFX_PROVIDER=angel needs ANGEL_TOKENS, e.g. NSE:SBIN-EQ=NSE:3045")
        return cast(MarketDataProvider, AngelProvider(credentials_from_env(e), tokens))  # Angel aliases depth/quote streams to the tick stream
    raise ValueError(f"OFX_PROVIDER must be synthetic, delta or angel, got {name!r}")
