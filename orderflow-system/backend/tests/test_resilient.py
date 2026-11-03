import asyncio

import pytest

from ofx.domain import AggressorSide as S
from ofx.providers.base import ProviderUnsupported
from ofx.providers.resilient import FatalStreamError, backoff_delay, resilient_trades
from tests.conftest import tr


def run(coro):
    return asyncio.run(coro)


async def collect(gen, n=None):
    out = []
    async for t in gen:
        out.append(t)
        if n and len(out) >= n:
            break
    return out


def factory_of(*scripts):
    """Each script is a list of Trades or Exceptions yielded/raised in order; one script per connection."""
    it = iter(scripts)

    def make():
        script = next(it)

        async def g():
            for x in script:
                if isinstance(x, BaseException):
                    raise x
                yield x
        return g()
    return make


async def nosleep(_):
    return None


def test_backoff_is_capped_and_jittered():
    assert backoff_delay(1, rand=lambda: 0.5) == 0.5
    assert backoff_delay(3, rand=lambda: 0.5) == 2.0
    assert backoff_delay(50, cap=15, rand=lambda: 1.0) == pytest.approx(18.0)  # cap * 1.2
    assert backoff_delay(50, cap=15, rand=lambda: 0.0) == pytest.approx(12.0)


def test_reconnects_after_error_and_renumbers_seq():
    a, b, c = (tr(i, 100 + i, 1, S.ASK, 99) for i in (1, 2, 3))
    ev = []
    f = factory_of([a, ConnectionResetError("drop")], [b, c])
    out = run(collect(resilient_trades(f, sleep=nosleep, on_event=lambda k, d: ev.append(k), max_failures=3), 3))
    assert [t.price for t in out] == [101, 102, 103] and [t.seq for t in out] == [1, 2, 3]
    assert ev[:3] == ["connected", "disconnected", "reconnected"]


def test_replay_after_reconnect_is_dropped_but_repeats_in_normal_flow_are_kept():
    p1, p2 = tr(1, 100, 1, S.ASK, 1), tr(2, 101, 1, S.ASK, 2)
    same = tr(2, 101, 1, S.ASK, 3)  # genuine second print identical in ts/price/qty, in normal flow
    new = tr(3, 102, 1, S.BID, 4)
    f = factory_of([p1, p2, same, ConnectionError("x")], [p1, p2, same, new])  # snapshot replays all three, then a new print
    out = run(collect(resilient_trades(f, sleep=nosleep), 4))
    assert [t.price for t in out] == [100, 101, 101, 102]  # duplicates inside the first connection survive; replay removed


def test_stream_end_counts_as_disconnect_and_max_failures_gives_up():
    f = factory_of([], [], [])
    with pytest.raises(ConnectionError, match="failed 3 times"):
        run(collect(resilient_trades(f, sleep=nosleep, max_failures=3)))


def test_failure_counter_resets_after_data():
    a, b = tr(1, 100, 1, S.ASK, 1), tr(2, 101, 1, S.ASK, 2)
    f = factory_of([a, OSError("x")], [OSError("y")], [b])  # 2 failures total but never 2 in a row without data
    out = run(collect(resilient_trades(f, sleep=nosleep, max_failures=3), 2))
    assert len(out) == 2


def test_stale_connection_is_recycled():
    b = tr(2, 101, 1, S.ASK, 2)

    def make():
        calls = getattr(make, "n", 0)
        make.n = calls + 1

        async def g():
            if calls == 0:
                await asyncio.sleep(10)  # silent half-open socket
                yield b
            else:
                yield b
        return g()
    out = run(collect(resilient_trades(make, stale_after=0.05, sleep=nosleep), 1))
    assert out[0].price == 101 and make.n == 2


@pytest.mark.parametrize("exc", [FatalStreamError("bad credentials"), ProviderUnsupported("nope")])
def test_fatal_errors_are_not_retried(exc):
    with pytest.raises(type(exc)):
        run(collect(resilient_trades(factory_of([exc]), sleep=nosleep)))


def test_run_ingest_resilient_publishes_status_events():
    from datetime import timedelta

    from ofx.api.hub import Hub
    from ofx.ingest import run_ingest
    from ofx.providers.base import Capabilities
    calls = {"n": 0}

    class P:
        capabilities = Capabilities("fake", True, True, 0, False, False)

        async def stream_trades(self, iid):
            calls["n"] += 1
            if calls["n"] == 1:
                yield tr(1, 100, 1, S.ASK, 1)
                raise ConnectionError("drop")
            if calls["n"] > 2:
                raise FatalStreamError("stop")
            yield tr(2, 101, 1, S.ASK, 2)

    async def go():
        hub = Hub()
        cl = hub.subscribe("X:footprint")
        # the second connection ends too, so cap failures to end the run
        from ofx.providers import resilient as r
        orig = r.resilient_trades
        r.resilient_trades = lambda fac, **kw: orig(fac, **{**kw, "sleep": nosleep, "max_failures": 2})
        try:
            await run_ingest(P(), "X", 1.0, timedelta(minutes=1), hub, resilient=True)
        except FatalStreamError:
            pass
        finally:
            r.resilient_trades = orig
        msgs = []
        while not cl.queue.empty():
            msgs.append(cl.queue.get_nowait())
        return msgs
    msgs = run(go())
    states = [m["state"] for m in msgs if m.get("type") == "status"]
    assert "disconnected" in states and "reconnected" in states
