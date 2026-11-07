import os

os.environ.setdefault("OFX_NO_DOTENV", "1")  # never load a developer's real backend/.env when tests import ofx.main
os.environ.setdefault("OFX_PROVIDER", "synthetic")

from datetime import UTC, datetime, timedelta

from ofx.domain import AggressorSide, Trade

T0 = datetime(2026, 1, 5, 4, 0, tzinfo=UTC)


def tr(sec: float, price: float, qty: float, side: AggressorSide = AggressorSide.ASK, seq: int = 0, method: str = "exchange") -> Trade:
    return Trade(T0 + timedelta(seconds=sec), price, qty, side, seq, method)
