"""
In-memory event bus для SSE: lead_created, lead_updated.
Подписчики получают события в реальном времени.
"""
import asyncio
import json
from typing import Any

_subscribers: list[asyncio.Queue] = []


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.append(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    if q in _subscribers:
        _subscribers.remove(q)


async def emit(event_type: str, payload: dict[str, Any]) -> None:
    """Отправить событие всем подписчикам SSE."""
    data = json.dumps({"event": event_type, "data": payload}, ensure_ascii=False)
    for q in list(_subscribers):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass
