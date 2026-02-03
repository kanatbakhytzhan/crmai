"""
CRM v2: Server-Sent Events (SSE) — realtime lead_created / lead_updated.
GET /api/events/stream (Bearer auth). Если SSE недоступно — фронт может продолжать polling.
"""
import asyncio
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from app.api.deps import get_current_user
from app.database.models import User
from app.services.events_bus import subscribe, unsubscribe

router = APIRouter(tags=["Events"])


async def _event_generator(user_id: int):
    """Генератор SSE: держит соединение открытым, отдаёт события."""
    q = subscribe()
    try:
        yield "data: {\"event\": \"connected\", \"user_id\": " + str(user_id) + "}\n\n"
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=30.0)
                yield f"data: {msg}\n\n"
            except asyncio.TimeoutError:
                yield "data: {\"event\": \"ping\"}\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        unsubscribe(q)


@router.get("/events/stream")
async def stream_events(
    current_user: User = Depends(get_current_user),
):
    """
    SSE поток: lead_created, lead_updated. Auth: Bearer.
    Подключение держим открытым; при отмене клиента отписываемся.
    """
    return StreamingResponse(
        _event_generator(current_user.id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
