"""
ChatFlow webhook: GET/POST /api/chatflow/webhook, GET /api/chatflow/ping.
Принимает входящие сообщения от ChatFlow.kz, формирует ответ (OpenAI или echo) и отправляет через send-text.
"""
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Request

from app.services import chatflow_client
from app.services import openai_service

router = APIRouter()
log = logging.getLogger(__name__)


def _normalize_jid(jid: str) -> str:
    """Привести jid к формату <digits>@s.whatsapp.net (убрать +, пробелы, скобки)."""
    if not jid:
        return ""
    s = str(jid).strip()
    if "@" in s:
        return s
    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return s
    return f"{digits}@s.whatsapp.net"


def _first(d: Any, *keys: str) -> Any:
    """Первое непустое значение из d.get(k) для ключей keys."""
    if d is None or not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def extract_incoming(data: dict[str, Any] | None) -> tuple[str, str]:
    """
    Извлечь jid и текст из входящего JSON максимально устойчиво.
    Поддерживает плоские поля и вложенные (message.text, data.msg, payload.text и т.п.).
    """
    if not data or not isinstance(data, dict):
        return "", ""

    jid = (
        _first(data, "jid", "chatId", "chat_id", "from", "sender", "phone")
        or _first(data.get("message") or {}, "from", "jid")
        or _first(data.get("data") or {}, "jid", "from")
        or _first(data.get("payload") or {}, "jid", "from")
    )
    if isinstance(jid, dict):
        jid = jid.get("id") or jid.get("jid") or str(jid)
    jid = str(jid).strip() if jid else ""

    text = (
        _first(data, "msg", "text", "body")
        or _first(data.get("message") or {}, "text", "body")
        or _first(data.get("data") or {}, "msg", "text")
        or _first(data.get("payload") or {}, "text", "body")
    )
    if isinstance(text, dict):
        text = text.get("body") or text.get("text") or str(text)
    text = str(text).strip() if text else ""

    return _normalize_jid(jid), text


@router.get("/webhook")
async def chatflow_webhook_get():
    """ChatFlow webhook GET — проверка доступности."""
    return {"ok": True}


@router.get("/ping")
async def chatflow_ping():
    """Быстрая проверка деплоя ChatFlow."""
    return {"ok": True, "pong": True}


@router.post("/webhook")
async def chatflow_webhook_post(request: Request):
    """ChatFlow webhook POST — принять JSON, извлечь jid/text, сформировать ответ, отправить через send-text."""
    body = await request.body()
    print("[CHATFLOW] RAW:", body[:2000])

    data = None
    try:
        data = json.loads(body) if body else None
    except Exception as e:
        print("[CHATFLOW] JSON parse error:", repr(e))

    print("[CHATFLOW] INCOMING JSON:", data)

    if data is None:
        return {"ok": True}

    jid, text = extract_incoming(data)
    if not text:
        return {"ok": True}

    if not jid:
        log.warning("[CHATFLOW] INCOMING: jid not found in payload")
        return {"ok": True}

    reply: str
    try:
        messages = [{"role": "user", "content": text}]
        response_text, _ = await openai_service.chat_with_gpt(messages, use_functions=True)
        reply = (response_text or "").strip() or f"Принял: {text}"
    except Exception as e:
        log.warning("[CHATFLOW] OpenAI fallback: %s", type(e).__name__)
        reply = f"Принял: {text}"

    try:
        await chatflow_client.send_text(jid, reply)
        log.info("[CHATFLOW] SEND ok jid=%s", jid[:20] + "..." if len(jid) > 20 else jid)
    except Exception as e:
        log.error("[CHATFLOW] ERROR send_text: %s", type(e).__name__)

    return {"ok": True}
