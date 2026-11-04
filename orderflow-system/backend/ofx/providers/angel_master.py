"""Angel One instrument master: search by name/symbol so any listed stock, index or future can be charted.

The master is a public JSON file (UNVERIFIED shape, recalled from the SmartAPI docs; confirm with scripts/smoke_live.py):
  [{"token":"2885","symbol":"RELIANCE-EQ","name":"RELIANCE","expiry":"","strike":"-1.000000","lotsize":"1",
    "instrumenttype":"","exch_seg":"NSE","tick_size":"5.000000"}, ...]   tick_size is in paise (5.0 -> Rs 0.05).
Only NSE/BSE cash equities and indices, NFO index/stock futures and MCX futures are kept (the file has >100k rows).
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
KEEP_FUT = {"FUTIDX", "FUTSTK", "FUTCOM"}


@dataclass(frozen=True)
class Scrip:
    iid: str
    exchange: str  # NSE | BSE | NFO | MCX
    token: str
    symbol: str  # trading symbol, e.g. RELIANCE-EQ
    name: str  # underlying name, e.g. RELIANCE
    kind: str  # equity | index | future
    tick_size: float
    lot_size: float
    expiry: str


def parse_master(rows: Iterable[Mapping[str, Any]]) -> list[Scrip]:
    out: list[Scrip] = []
    for r in rows:
        exch, sym, tok, itype = str(r.get("exch_seg", "")), str(r.get("symbol", "")), str(r.get("token", "")), str(r.get("instrumenttype", ""))
        if not (exch and sym and tok):
            continue
        if exch in ("NSE", "BSE") and sym.endswith("-EQ"):
            kind = "equity"
        elif exch in ("NSE", "BSE") and itype == "AMXIDX":
            kind = "index"
        elif exch in ("NFO", "MCX") and itype in KEEP_FUT:
            kind = "future"
        else:
            continue
        try:
            tick = float(r.get("tick_size") or 0) / 100.0
            lot = float(r.get("lotsize") or 1)
        except ValueError:
            continue
        out.append(Scrip(f"{exch}:{sym}", exch, tok, sym, str(r.get("name", "")), kind, tick if tick > 0 else 0.05, lot or 1.0, str(r.get("expiry", ""))))
    return out


def search(scrips: list[Scrip], q: str, limit: int = 20) -> list[Scrip]:
    """Rank: exact symbol/name, then prefix, then substring; indices and equities before futures; stable by symbol."""
    needle = q.strip().upper()
    if not needle:
        return []
    kind_rank = {"index": 0, "equity": 1, "future": 2}
    scored: list[tuple[int, int, str, Scrip]] = []
    for s in scrips:
        sym, name = s.symbol.upper(), s.name.upper()
        base = sym[:-3] if sym.endswith("-EQ") else sym
        if needle in (base, name):
            score = 0
        elif base.startswith(needle) or name.startswith(needle):
            score = 1
        elif needle in base or needle in name:
            score = 2
        else:
            continue
        scored.append((score, kind_rank[s.kind], s.symbol, s))
    scored.sort(key=lambda t: t[:3])
    return [t[3] for t in scored[:limit]]


class MasterCache:
    """Downloads the master once, lazily, and shares it. `loader` is injectable for tests."""

    def __init__(self, loader: Any = None) -> None:
        self._loader = loader or self._download
        self._scrips: list[Scrip] | None = None
        self._by_iid: dict[str, Scrip] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    async def _download() -> list[Mapping[str, Any]]:
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.get(MASTER_URL)
            r.raise_for_status()
            return r.json()  # type: ignore[no-any-return]

    async def scrips(self) -> list[Scrip]:
        async with self._lock:
            if self._scrips is None:
                self._scrips = parse_master(await self._loader())
                self._by_iid = {s.iid: s for s in self._scrips}
            return self._scrips

    async def get(self, iid: str) -> Scrip | None:
        await self.scrips()
        return self._by_iid.get(iid)
