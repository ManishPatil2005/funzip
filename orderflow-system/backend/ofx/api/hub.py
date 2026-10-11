"""WebSocket fan-out hub with bounded per-client queues.

Backpressure policy: a slow client gets its OLDEST message dropped (never blocks the
producer or other clients) and a `dropped` counter is sent so the UI can show a gap.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any


class Client:
    def __init__(self, maxsize: int) -> None:
        self.queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize)
        self.dropped = 0


class Hub:
    def __init__(self, queue_size: int = 256) -> None:
        self._topics: dict[str, set[Client]] = defaultdict(set)
        self._size = queue_size

    def subscribe(self, topic: str) -> Client:
        c = Client(self._size)
        self._topics[topic].add(c)
        return c

    def unsubscribe(self, topic: str, c: Client) -> None:
        self._topics[topic].discard(c)

    def publish(self, topic: str, msg: dict[str, Any]) -> None:
        for c in list(self._topics.get(topic, ())):
            if c.queue.full():
                c.queue.get_nowait()
                c.dropped += 1
                msg = {**msg, "dropped": c.dropped}
            c.queue.put_nowait(msg)

    def count(self, topic: str) -> int:
        return len(self._topics.get(topic, ()))
