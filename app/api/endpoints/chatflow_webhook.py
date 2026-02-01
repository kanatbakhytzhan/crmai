"""
ChatFlow webhook: GET и POST /api/chatflow/webhook.
"""
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/webhook")
async def chatflow_webhook_get():
    """ChatFlow webhook GET — проверка доступности."""
    return {"ok": True}


@router.post("/webhook")
async def chatflow_webhook_post(request: Request):
    """ChatFlow webhook POST — принять JSON, залогировать и вернуть ok."""
    try:
        data = await request.json()
    except Exception:
        data = None
    print("[CHATFLOW] INCOMING:", data)
    return {"ok": True}
