"""
ChatFlow webhook: GET/POST /api/chatflow/webhook, GET /api/chatflow/ping.

Логика:
- Контекст по remoteJid (conversation_messages, channel=chatflow), без повторного приветствия.
- Текст: data["message"]; голосовые: mediaData.url или mediaData.base64 → Whisper → текст.
- Ответы только из backend через ChatFlow API send-text (не через Flow "Text message").
- Дедупликация по messageId (external_message_id в conversation_messages).

ENV: CHATFLOW_TOKEN, CHATFLOW_INSTANCE_ID, OPENAI_API_KEY (токены не в коде).

Ручная проверка (curl):
  curl -X POST http://localhost:8000/api/chatflow/webhook \\
    -H "Content-Type: application/json" \\
    -d '{"messageType":"text","message":"Салем","metadata":{"remoteJid":"77768776637@s.whatsapp.net","messageId":"ABC123","timestamp":1769970129}}'
"""
import base64
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.services import chatflow_client, conversation_service, openai_service

router = APIRouter()
log = logging.getLogger(__name__)

CONTEXT_LIMIT = 15
VOICE_TYPES = ("audio", "voice", "ptt", "voice_note")
MEDIA_DOWNLOAD_TIMEOUT = 25.0
MEDIA_DOWNLOAD_RETRIES = 2

# Дополнение к system prompt при наличии истории: не повторять приветствия
EXTRA_SYSTEM_CONTEXT = (
    "Если в истории уже есть сообщения, не повторяй приветствие — отвечай по сути последнего сообщения."
)


def parse_incoming_payload(data: dict[str, Any] | None) -> tuple[str, str, str, str]:
    """
    Извлечь из payload ChatFlow: remote_jid, msg_id, message_type, text (для text).
    Returns: (remote_jid, msg_id, message_type, text)
    """
    if not data or not isinstance(data, dict):
        return "", "", "", ""
    meta = data.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    remote_jid = (meta.get("remoteJid") or "").strip()
    msg_id = (meta.get("messageId") or "").strip()
    msg_type = (data.get("messageType") or "text").strip().lower() if data.get("messageType") else "text"
    text = data.get("message")
    if isinstance(text, dict):
        text = text.get("text") or text.get("body") or str(text)
    text = (text or "").strip() if text is not None else ""
    return remote_jid, msg_id, msg_type, text


def _suffix_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".ogg"
    ct = (content_type or "").lower()
    if "ogg" in ct or "opus" in ct:
        return ".ogg"
    if "mpeg" in ct or "mp3" in ct:
        return ".mp3"
    if "m4a" in ct or "mp4" in ct:
        return ".m4a"
    if "wav" in ct:
        return ".wav"
    if "webm" in ct:
        return ".webm"
    return ".ogg"


async def _get_audio_bytes_from_payload(data: dict[str, Any]) -> tuple[bytes | None, str]:
    """
    Достать аудио из data: mediaData.url (GET) или mediaData.base64.
    Returns: (audio_bytes, suffix). (None, "") при ошибке.
    """
    media = data.get("mediaData") or data.get("media") or {}
    if not isinstance(media, dict):
        log.warning("[CHATFLOW] mediaData not a dict: %s", type(media))
        return None, ""

    url = (media.get("url") or media.get("link") or "").strip()
    b64 = media.get("base64") or media.get("data")
    if url:
        for attempt in range(MEDIA_DOWNLOAD_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=MEDIA_DOWNLOAD_TIMEOUT) as client:
                    resp = await client.get(url)
                resp.raise_for_status()
                body = resp.content
                ct = resp.headers.get("content-type")
                suffix = _suffix_from_content_type(ct)
                log.info("[CHATFLOW] media downloaded url len=%s content_type=%s", len(body), ct)
                return body, suffix
            except Exception as e:
                log.warning("[CHATFLOW] media download attempt %s failed: %s", attempt + 1, type(e).__name__)
        return None, ""
    if b64 is not None:
        try:
            if isinstance(b64, str):
                body = base64.b64decode(b64, validate=True)
            else:
                body = bytes(b64)
            log.info("[CHATFLOW] media decoded base64 len=%s", len(body))
            return body, ".ogg"
        except Exception as e:
            log.warning("[CHATFLOW] base64 decode failed: %s", type(e).__name__)
        return None, ""
    log.warning("[CHATFLOW] mediaData has no url or base64")
    return None, ""


async def _transcribe_voice_and_get_text(data: dict[str, Any]) -> str | None:
    """Скачать/декодировать аудио из payload, транскрибировать через Whisper. None при ошибке."""
    audio_bytes, suffix = await _get_audio_bytes_from_payload(data)
    if not audio_bytes or len(audio_bytes) < 100:
        return None
    try:
        text = await openai_service.transcribe_audio_from_bytes(audio_bytes, suffix=suffix)
        return (text or "").strip() or None
    except Exception as e:
        log.warning("[CHATFLOW] transcribe_audio_from_bytes failed: %s", type(e).__name__)
        return None


async def _send_reply_and_return_ok(jid: str, reply: str) -> None:
    """Отправить ответ в ChatFlow, при ошибке только залогировать."""
    try:
        result = await chatflow_client.send_text(jid, reply)
        log.info("[CHATFLOW] send-to-chatflow status=%s", result.get("status_code"))
    except Exception as e:
        log.error("[CHATFLOW] send_text error: %s", type(e).__name__, exc_info=True)


@router.get("/webhook")
async def chatflow_webhook_get():
    """ChatFlow webhook GET — проверка доступности (CORS OPTIONS обрабатывается в main)."""
    return {"ok": True}


@router.get("/ping")
async def chatflow_ping():
    """Быстрая проверка деплоя ChatFlow."""
    return {"ok": True, "pong": True}


@router.post("/webhook")
async def chatflow_webhook_post(request: Request, db: AsyncSession = Depends(get_db)):
    """
    1) Парсинг remote_jid, msg_id, messageType, message.
    2) Дедуп по msg_id → return {"ok": True, "dedup": True}.
    3) user_text: text | voice (mediaData → Whisper) | иначе ответ "Пока понимаю только текст и голосовые."
    4) При ошибке голосового → ответ "Не получилось распознать голосовое, напишите текстом.", return ok.
    5) Сохранить входящее в БД (raw_json), загрузить историю по remote_jid (последние 15), LLM, сохранить ответ, send-text.
    """
    body = await request.body()
    data = None
    try:
        data = json.loads(body) if body else None
    except Exception as e:
        log.warning("[CHATFLOW] JSON parse error: %s", repr(e))

    if data is None or not isinstance(data, dict):
        return {"ok": True}

    remote_jid, msg_id, msg_type, text_from_message = parse_incoming_payload(data)
    log.info("[CHATFLOW] msg_type=%s remote_jid=%s msg_id=%s", msg_type, remote_jid, msg_id)

    if not remote_jid:
        return {"ok": True}

    # Дедупликация
    if msg_id:
        existing = await conversation_service.get_message_by_external_id(db, msg_id)
        if existing:
            log.info("[CHATFLOW] dedup hit msg_id=%s", msg_id)
            return {"ok": True, "dedup": True}

    # Извлечь user_text в зависимости от типа
    user_text: str | None = None
    if msg_type == "text":
        user_text = text_from_message or None
    elif msg_type in VOICE_TYPES:
        transcript = await _transcribe_voice_and_get_text(data)
        if transcript:
            user_text = transcript
            log.info("[CHATFLOW] transcript length=%s", len(user_text))
        else:
            await _send_reply_and_return_ok(
                remote_jid, "Не получилось распознать голосовое, напишите текстом."
            )
            return {"ok": True}
    else:
        await _send_reply_and_return_ok(
            remote_jid, "Пока понимаю только текст и голосовые."
        )
        return {"ok": True}

    if not (user_text and user_text.strip()):
        return {"ok": True}

    # Get or create conversation (channel=chatflow, external_id=remote_jid)
    try:
        conv = await conversation_service.get_or_create_conversation(
            db, tenant_id=None, channel="chatflow", external_id=remote_jid, phone_number_id=""
        )
    except Exception as e:
        log.error("[CHATFLOW] get_or_create_conversation error: %s", type(e).__name__, exc_info=True)
        return {"ok": True}

    # Сохранить входящее сообщение (raw_json для отладки)
    try:
        await conversation_service.append_user_message(
            db, conv.id, user_text, raw_json=data, external_message_id=msg_id or None
        )
    except Exception as e:
        log.error("[CHATFLOW] append_user_message error: %s", type(e).__name__, exc_info=True)
        return {"ok": True}

    messages_for_gpt = await conversation_service.build_context_messages(db, conv.id, limit=CONTEXT_LIMIT)
    log.info("[CHATFLOW] messages loaded count=%s", len(messages_for_gpt))

    # Дополнение к system: не повторять приветствия при наличии контекста
    extra_system = EXTRA_SYSTEM_CONTEXT if len(messages_for_gpt) > 1 else None

    try:
        response_text, _ = await openai_service.chat_with_gpt(
            messages_for_gpt, use_functions=True, extra_system_content=extra_system
        )
        reply = (response_text or "").strip() or "Чем могу помочь?"
        log.info("[CHATFLOW] openai ok reply_len=%s", len(reply))
    except Exception as e:
        log.error("[CHATFLOW] OpenAI error: %s", type(e).__name__, exc_info=True)
        reply = "Чем могу помочь?"

    try:
        await conversation_service.append_assistant_message(db, conv.id, reply)
    except Exception as e:
        log.warning("[CHATFLOW] append_assistant_message error: %s", type(e).__name__)

    await _send_reply_and_return_ok(remote_jid, reply)
    return {"ok": True}
