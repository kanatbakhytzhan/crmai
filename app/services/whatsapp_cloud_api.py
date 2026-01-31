"""
WhatsApp Cloud API: отправка текстовых ответов (опционально, по умолчанию выключено).
Используется только при WHATSAPP_SEND_ENABLED=true и заданном WHATSAPP_ACCESS_TOKEN.
"""
import logging
from typing import Any

import httpx

from app.core.config import get_settings

log = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 1000


async def send_text_message(phone_number_id: str, to: str, text: str) -> dict[str, Any]:
    """
    Отправить текстовое сообщение в WhatsApp через Cloud API.
    - Если WHATSAPP_SEND_ENABLED=false → {"skipped": True, "reason": "disabled"}
    - Если WHATSAPP_ACCESS_TOKEN не задан → {"skipped": True, "reason": "missing_token"}
    - Иначе POST на {GRAPH_BASE}/{API_VERSION}/{phone_number_id}/messages с Bearer.
    Текст обрезается до MAX_TEXT_LENGTH. Токен в логах не выводится.
    """
    settings = get_settings()
    if (getattr(settings, "whatsapp_send_enabled", "false") or "false").upper() != "TRUE":
        return {"skipped": True, "reason": "disabled"}
    token = getattr(settings, "whatsapp_access_token", None)
    if not token or not str(token).strip():
        return {"skipped": True, "reason": "missing_token"}

    phone_number_id = str(phone_number_id).strip()
    to = str(to).strip()
    body_text = (text or "")[:MAX_TEXT_LENGTH]

    base = (getattr(settings, "whatsapp_graph_base", None) or "https://graph.facebook.com").rstrip("/")
    version = (getattr(settings, "whatsapp_api_version", None) or "v20.0").strip()
    url = f"{base}/{version}/{phone_number_id}/messages"

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body_text},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 200 and resp.status_code < 300:
            data = resp.json()
            message_id = (data.get("messages") or [{}])[0].get("id") if isinstance(data.get("messages"), list) else None
            return {"ok": True, "message_id": message_id}
        try:
            err_body = resp.json()
            err_msg = str(err_body.get("error", {}).get("message", resp.text))[:200]
        except Exception:
            err_msg = resp.text[:200] if resp.text else str(resp.status_code)
        return {"ok": False, "error": err_msg, "status_code": resp.status_code}
    except Exception as e:
        log.warning("[WA][SEND] request failed: %s", type(e).__name__)
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
