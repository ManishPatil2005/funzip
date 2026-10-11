"""Delta Exchange adapter SKELETON.

ASSUMPTIONS (unverified against live payloads; confirm with a read-only key before use):
  A1. Signature = HMAC-SHA256(secret, method + timestamp + path + query + body), hex digest.
  A2. Signature timestamp must be within ~5 seconds of server time.
  A3. The public trades channel may carry a taker/aggressor side. If it does not, trades are
      classified with the tick rule and labelled ESTIMATED.
Nothing here performs network I/O; `signed_headers` is a pure helper so it can be unit-tested.
"""
from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping

from ofx.providers.base import Capabilities, ProviderUnsupported

CAPABILITIES = Capabilities(
    name="delta_exchange", trades=True, aggressor_flag=False,  # A3: flipped to True only after verification
    depth_levels=20, historical_trades=False, historical_candles=True,
    notes="Crypto derivatives. Aggressor flag unverified (A3). Rate limit: weight-based (see ADR).")


def sign(secret: str, method: str, timestamp: str, path: str, query: str = "", body: str = "") -> str:
    msg = f"{method.upper()}{timestamp}{path}{query}{body}"
    return hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()


def signed_headers(api_key: str, secret: str, method: str, timestamp: str, path: str,
                   query: str = "", body: str = "") -> Mapping[str, str]:
    return {"api-key": api_key, "timestamp": timestamp, "signature": sign(secret, method, timestamp, path, query, body),
            "User-Agent": "ofx/0.1", "Content-Type": "application/json"}


class DeltaProvider:
    capabilities = CAPABILITIES

    def __init__(self, api_key: str, secret: str) -> None:
        self._key, self._secret = api_key, secret

    def __repr__(self) -> str:  # never leak credentials into logs
        return "DeltaProvider(api_key=***, secret=***)"

    async def instruments(self):  # pragma: no cover - network skeleton
        raise ProviderUnsupported("network adapter not implemented in skeleton")

    trades = candles = stream_trades = stream_depth = stream_quotes = instruments  # type: ignore[assignment]
