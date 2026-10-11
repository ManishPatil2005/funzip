"""REST API. Every data endpoint requires an API key (see core.security)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app import __version__, db
from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.data.provider import ALLOWED_INTERVALS, DataError, get_provider
from app.data.universe import INSTRUMENTS, UNIVERSES, Instrument, SYMBOL_RE, lookup
from app.profile import market_profile as mp
from app.strategies import builder, scanner
from app.strategies.builtin import REGISTRY, StrategyError, catalogue, clean_params

log = logging.getLogger("scanner.api")

public = APIRouter()
api = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])

PERIODS_FOR = {
    "1m": ("1d", "5d"),
    "5m": ("1d", "5d", "1mo"),
    "15m": ("1d", "5d", "1mo"),
    "30m": ("1d", "5d", "1mo"),
    "60m": ("5d", "1mo", "3mo", "6mo", "1y", "2y"),
    "1h": ("5d", "1mo", "3mo", "6mo", "1y", "2y"),
    "1d": ("1mo", "3mo", "6mo", "1y", "2y", "5y"),
}


def _check_range(interval: str, period: str) -> None:
    if interval not in PERIODS_FOR:
        raise HTTPException(422, f"interval must be one of {list(PERIODS_FOR)}")
    if period not in PERIODS_FOR[interval]:
        raise HTTPException(422, f"period for {interval} must be one of {list(PERIODS_FOR[interval])}")


# ------------------------------------------------------------------------ health
@public.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


@public.get("/readyz", include_in_schema=False)
def readyz():
    try:
        db.ping()
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "database unavailable")
    return {"status": "ready", "version": __version__}


# -------------------------------------------------------------------------- meta
@api.get("/meta")
def meta(settings: Settings = Depends(get_settings)):
    return {
        "version": __version__,
        "universes": {k: len(v) for k, v in UNIVERSES.items()},
        "intervals": PERIODS_FOR,
        "max_scan_symbols": settings.max_scan_symbols,
        "data_provider": settings.data_provider,
        "mcx_note": "MCX symbols use global futures proxies via Yahoo Finance; prices are USD, not MCX INR.",
    }


@api.get("/instruments")
def instruments(exchange: Annotated[str | None, Query(pattern="^(NSE|MCX)$")] = None):
    items = [i for i in INSTRUMENTS.values() if not exchange or i.exchange == exchange]
    return [{"symbol": i.symbol, "name": i.name, "exchange": i.exchange, "segment": i.segment, "proxy": i.proxy}
            for i in items]


@api.get("/strategies")
def strategies():
    return {"builtin": catalogue(), "templates": builder.TEMPLATES}


# -------------------------------------------------------------------------- scan
class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    universe: str | None = Field(default="NIFTY50", max_length=20)
    symbols: list[str] | None = Field(default=None, max_length=100)
    interval: str = "1d"
    period: str = "1y"
    strategies: list[str] = Field(default_factory=list, max_length=30)
    params: dict[str, dict[str, float]] = Field(default_factory=dict)
    custom: list[str] = Field(default_factory=list, max_length=10)
    inline_custom: list[dict] = Field(default_factory=list, max_length=3)
    signal: str | None = Field(default=None, pattern="^(BUY|SELL)$")

    @field_validator("symbols")
    @classmethod
    def check_symbols(cls, v):
        if v is None:
            return v
        for s in v:
            if not isinstance(s, str) or not SYMBOL_RE.match(s.upper().replace("NSE:", "")):
                raise ValueError(f"Invalid symbol: {s!r}")
        return v


@api.post("/scan")
def scan(req: ScanRequest, settings: Settings = Depends(get_settings)):
    _check_range(req.interval, req.period)
    if req.symbols:
        insts: list[Instrument] = []
        for s in dict.fromkeys(x.upper() for x in req.symbols):
            inst = lookup(s)
            if inst is None:
                raise HTTPException(422, f"Unknown symbol {s}. Use NSE:SYMBOL for other NSE equities.")
            insts.append(inst)
    else:
        names = UNIVERSES.get((req.universe or "").upper())
        if names is None:
            raise HTTPException(422, f"universe must be one of {list(UNIVERSES)}")
        insts = [INSTRUMENTS[n] for n in names]
    if len(insts) > settings.max_scan_symbols:
        raise HTTPException(422, f"At most {settings.max_scan_symbols} symbols per scan")

    for sid in req.strategies:
        if sid not in REGISTRY:
            raise HTTPException(422, f"Unknown strategy '{sid}'")
        try:
            clean_params(REGISTRY[sid], req.params.get(sid))
        except StrategyError as exc:
            raise HTTPException(422, str(exc))

    customs: list[builder.CustomStrategy] = []
    for name in req.custom:
        stored = db.get_strategy(name)
        if stored is None:
            raise HTTPException(404, f"Saved strategy '{name}' not found")
        customs.append(builder.parse(stored))
    for raw in req.inline_custom:
        try:
            customs.append(builder.parse(raw))
        except ValidationError as exc:
            raise HTTPException(422, _errors(exc))
    if not req.strategies and not customs:
        raise HTTPException(422, "Select at least one strategy")

    rows = scanner.scan(insts, req.interval, req.period, req.strategies, req.params, customs)
    if req.signal:
        rows = [r for r in rows if any(h["signal"] == req.signal for h in r["hits"])]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "interval": req.interval, "period": req.period, "scanned": len(insts),
        "matches": sum(1 for r in rows if r["hits"]), "results": rows,
    }


# ------------------------------------------------------------ custom strategies
def _errors(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])


@api.get("/custom")
def custom_list():
    return db.list_strategies()


@api.post("/custom/validate")
def custom_validate(payload: dict):
    try:
        strat = builder.parse(payload)
    except ValidationError as exc:
        raise HTTPException(422, _errors(exc))
    return {"valid": True, "name": strat.name}


@api.post("/custom", status_code=201)
def custom_save(payload: dict):
    try:
        strat = builder.parse(payload)
    except ValidationError as exc:
        raise HTTPException(422, _errors(exc))
    try:
        db.save_strategy(strat.name, strat.model_dump(mode="json", exclude_none=True))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return {"saved": strat.name}


@api.delete("/custom/{name}")
def custom_delete(name: Annotated[str, Path(max_length=60)]):
    if not db.delete_strategy(name):
        raise HTTPException(404, "Strategy not found")
    return {"deleted": name}


@api.post("/custom/test")
def custom_test(payload: dict, symbol: str = Query("NIFTY50", max_length=30),
                interval: str = "1d", period: str = "1y"):
    """Evaluate a draft strategy on one symbol without saving it."""
    _check_range(interval, period)
    inst = _instrument_or_404(symbol)
    try:
        strat = builder.parse(payload)
    except ValidationError as exc:
        raise HTTPException(422, _errors(exc))
    df = _history(inst, interval, period)
    res = builder.evaluate(df, strat)
    return {"symbol": inst.symbol, "signal": res.signal, "reason": res.reason, "as_of": df.index[-1].isoformat(),
            "metrics": res.metrics}


# ----------------------------------------------------------------- market profile
def _instrument_or_404(symbol: str) -> Instrument:
    inst = lookup(symbol)
    if inst is None:
        raise HTTPException(404, f"Unknown symbol {symbol}. Use NSE:SYMBOL for other NSE equities.")
    return inst


def _history(inst: Instrument, interval: str, period: str):
    try:
        return get_provider().history(inst, interval, period)
    except DataError as exc:
        raise HTTPException(502, str(exc))


@api.get("/profile/{symbol}")
def profile(
    symbol: Annotated[str, Path(max_length=30)],
    interval: Annotated[str, Query(pattern="^(1m|5m|15m|30m)$")] = "30m",
    period: Annotated[str, Query(pattern="^(1d|5d|1mo)$")] = "1mo",
    period_minutes: Annotated[int, Query(ge=5, le=60)] = 30,
    date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
    lookback: Annotated[int, Query(ge=2, le=15)] = 6,
):
    _check_range(interval, period)
    inst = _instrument_or_404(symbol)
    df = _history(inst, interval, period)
    try:
        return mp.build_report(df, inst, period_minutes, date, lookback)
    except mp.ProfileError as exc:
        raise HTTPException(422, str(exc))


@api.get("/profile/{symbol}/ascii")
def profile_ascii(
    symbol: Annotated[str, Path(max_length=30)],
    interval: Annotated[str, Query(pattern="^(1m|5m|15m|30m)$")] = "30m",
    period: Annotated[str, Query(pattern="^(1d|5d|1mo)$")] = "1mo",
    date: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")] = None,
):
    report = profile(symbol, interval, period, 30, date, 6)
    return {"text": mp.render_ascii(report["profile"])}
