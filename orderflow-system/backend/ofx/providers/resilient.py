"""Reconnecting wrapper for live trade streams.

A raw provider stream ends (or hangs) the moment the socket drops, which would silently stop ingest. This wrapper
  * reconnects with capped exponential backoff and jitter, resetting the attempt counter after the first message,
  * treats silence longer than `stale_after` as a dead connection (half-open sockets raise nothing),
  * drops trades re-sent right after a reconnect (snapshot replays): only the leading run that matches recently seen prints
    is dropped, each earlier print consumed once, so genuine repeated prints in normal flow are never merged,
  * renumbers `seq` so it stays strictly increasing across reconnects,
  * never retries `ProviderUnsupported` or `FatalStreamError` (bad credentials, no entitlement): retrying cannot fix those.
Gaps are real: trades missed while disconnected are NOT backfilled here (providers differ); consumers are told via `on_event`.
ASSUMPTION (A18): a provider's replay after reconnect is a contiguous run of recent prints that match earlier ones on
(ts, price, qty). The run ends at the first print that does not match.
"""
from __future__ import annotations

import asyncio
import random
from collections import Counter, deque
from collections.abc import AsyncIterator, Callable
from dataclasses import replace

from ofx.domain import Trade
from ofx.providers.base import ProviderUnsupported


class FatalStreamError(RuntimeError):
    """Raised by an adapter for errors that a reconnect cannot fix (authentication, entitlement)."""


def backoff_delay(attempt: int, base: float = 0.5, cap: float = 15.0, rand: Callable[[], float] = random.random) -> float:
    """Capped exponential backoff with +-20% jitter; `attempt` starts at 1."""
    d = min(cap, base * 2 ** max(0, attempt - 1))
    return d * (0.8 + 0.4 * rand())


async def resilient_trades(
    factory: Callable[[], AsyncIterator[Trade]], *, stale_after: float = 30.0, base: float = 0.5, cap: float = 15.0,
    max_failures: int = 0, dedupe_window: int = 2000, on_event: Callable[[str, dict], None] | None = None,
    sleep: Callable[[float], object] = asyncio.sleep, rand: Callable[[], float] = random.random,
) -> AsyncIterator[Trade]:
    """`max_failures` consecutive failed connects end the stream with the last error (0 = retry forever)."""
    emit = on_event or (lambda _k, _d: None)
    recent: deque[tuple] = deque(maxlen=dedupe_window)
    replay: Counter[tuple] = Counter()
    replaying = False
    seq, failures, ever_connected = 0, 0, False
    while True:
        replay, replaying = Counter(recent), bool(recent)
        it = factory().__aiter__()
        got_any = False
        err: BaseException | None = None
        try:
            while True:
                try:
                    t = await asyncio.wait_for(it.__anext__(), stale_after)
                except StopAsyncIteration:
                    err = ConnectionError("stream ended")
                    break
                except TimeoutError:
                    err = TimeoutError(f"no data for {stale_after:g}s")
                    break
                if not got_any:
                    got_any, failures = True, 0
                    emit("connected" if not ever_connected else "reconnected", {})
                    ever_connected = True
                key = (t.ts, t.price, t.qty)
                if replaying:
                    if replay[key] > 0:
                        replay[key] -= 1
                        continue
                    replaying = False
                recent.append(key)
                seq += 1
                yield replace(t, seq=seq)
        except (ProviderUnsupported, FatalStreamError, asyncio.CancelledError):
            raise
        except Exception as e:  # noqa: BLE001 - any transport error means "reconnect"
            err = e
        finally:
            aclose = getattr(it, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001, S110 - closing a dead socket may itself fail
                    pass
        failures += 1
        if max_failures and failures >= max_failures:
            emit("giving_up", {"error": str(err), "failures": failures})
            raise ConnectionError(f"stream failed {failures} times: {err}") from err
        delay = backoff_delay(failures, base, cap, rand)
        emit("disconnected", {"error": str(err), "retry_in": round(delay, 2), "attempt": failures})
        await sleep(delay)  # type: ignore[misc]
