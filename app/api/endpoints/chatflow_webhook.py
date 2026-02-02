"""
ChatFlow webhook: GET/POST /api/chatflow/webhook, GET /api/chatflow/ping.

Логика:
- Единый ключ диалога — ТОЛЬКО data["metadata"]["remoteJid"] (jid). Номер из текста НЕ создаёт нового диалога.
- Контекст по jid (conversation_messages, channel=chatflow). Приветствие только при первой реплике (нет assistant в истории).
- Номер телефона берётся из jid (phone = jid.split("@")[0]). Бот НЕ просит номер — он уже известен.
- Если пользователь прислал номер текстом — распознаём, сохраняем в текущий lead.phone, продолжаем без повторного приветствия.
- Один активный lead на jid (NEW/IN_PROGRESS). Дедупликация по messageId.

ENV: CHATFLOW_TOKEN, CHATFLOW_INSTANCE_ID, OPENAI_API_KEY.
"""
import base64
import json
import logging
import re
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.database import crud
from app.services import chatflow_client, conversation_service, openai_service

router = APIRouter()
log = logging.getLogger(__name__)

CONTEXT_LIMIT = 15
VOICE_TYPES = ("audio", "voice", "ptt", "voice_note")
MEDIA_DOWNLOAD_TIMEOUT = 25.0
MEDIA_DOWNLOAD_RETRIES = 2

# Номер из jid — бот не просит номер
CHATFLOW_PHONE_CONTEXT = (
    "Контекст WhatsApp: номер телефона клиента уже известен — {phone}. "
    "НЕ проси номер и НЕ говори «дайте номер» / «на какой номер перезвонить». "
    "Спроси только имя если нужна заявка. Используй этот номер для заявки."
)
# При наличии истории — не повторять приветствие
EXTRA_SYSTEM_CONTEXT = (
    "Если в истории уже есть сообщения, не повторяй приветствие — отвечай по сути последнего сообщения."
)

PHONE_REGEX = re.compile(r"^\+?[\d\s\-()]{10,15}$")


def _parse_mute_command(text: str) -> str | None:
    """
    Команды: /stop, /start, /stop all, /start all (регистр не важен, пробелы схлопнуть).
    Возвращает: "stop" | "start" | "stop_all" | "start_all" | None.
    """
    raw = (text or "").strip().lower()
    raw = " ".join(raw.split())
    if not raw:
        return None
    if raw in ("/stop", "stop"):
        return "stop"
    if raw in ("/start", "start"):
        return "start"
    if raw in ("/stop all", "stop all"):
        return "stop_all"
    if raw in ("/start all", "start all"):
        return "start_all"
    return None


def _normalize_phone(text: str) -> str | None:
    r"""Распознать номер из текста (+?\d{10,15}). Вернуть нормализованный (+77...) или None."""
    if not text or not text.strip():
        return None
    s = text.strip()
    if not PHONE_REGEX.match(s):
        return None
    digits = re.sub(r"\D", "", s)
    if len(digits) < 10:
        return None
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+" + digits
    if len(digits) >= 10:
        return "+" + digits
    return None


async def _get_default_owner_id(db: AsyncSession) -> int | None:
    """Владелец лидов для ChatFlow (default_owner_email или первый пользователь)."""
    from app.core.config import get_settings
    settings = get_settings()
    default_email = getattr(settings, "default_owner_email", None)
    if default_email:
        user = await crud.get_user_by_email(db, email=default_email)
        if user:
            return user.id
    user = await crud.get_first_user(db)
    return user.id if user else None


async def _get_chatflow_tenant(db: AsyncSession):
    """Первый активный tenant для ChatFlow (ai_enabled, команды /stop /start)."""
    tenants = await crud.list_tenants(db, active_only=True)
    return tenants[0] if tenants else None


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

    # Если пользователь прислал номер текстом — сохранить в текущий lead.phone (не новый диалог)
    phone_from_jid = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    normalized_in_message = _normalize_phone(user_text)
    if normalized_in_message:
        try:
            owner_id = await _get_default_owner_id(db)
            if owner_id:
                bot_user = await crud.get_or_create_bot_user(db, user_id=remote_jid, owner_id=owner_id)
                active_lead = await crud.get_active_lead_by_bot_user(db, bot_user.id)
                if active_lead and (not active_lead.phone or active_lead.phone != normalized_in_message):
                    await crud.update_lead_phone(db, active_lead.id, normalized_in_message)
                    log.info("[CHATFLOW] lead phone updated lead_id=%s phone=%s", active_lead.id, normalized_in_message)
        except Exception as e:
            log.warning("[CHATFLOW] update lead phone: %s", type(e).__name__)

    # Tenant для ChatFlow: первый активный (ai_enabled, tenant_id для mute)
    tenant = await _get_chatflow_tenant(db)
    tenant_id = tenant.id if tenant else None
    ai_enabled = getattr(tenant, "ai_enabled", True) if tenant else True
    channel_cf = "chatflow"
    phone_number_id_cf = ""  # один инстанс ChatFlow — mute общий по external_id (remote_jid)

    # Команды /stop и /start — только этот чат (локальный переключатель)
    mute_cmd = _parse_mute_command(user_text or "")
    if mute_cmd and tenant_id is not None:
        if mute_cmd in ("stop", "start"):
            if mute_cmd == "stop":
                await crud.set_chat_mute(db, tenant_id, channel_cf, phone_number_id_cf, remote_jid, is_muted=True)
                log.info("[MUTE] chat set muted=true channel=%s phone_number_id=%s external_id=%s", channel_cf, phone_number_id_cf, remote_jid)
                reply = "✅ Ок. Я отключил автоответ AI в этом чате. Лиды продолжат сохраняться."
            else:
                await crud.set_chat_mute(db, tenant_id, channel_cf, phone_number_id_cf, remote_jid, is_muted=False)
                log.info("[MUTE] chat set muted=false channel=%s phone_number_id=%s external_id=%s", channel_cf, phone_number_id_cf, remote_jid)
                reply = "✅ Ок. Автоответ AI снова включён в этом чате."
            await _send_reply_and_return_ok(remote_jid, reply)
            return {"ok": True}
        if mute_cmd == "stop_all":
            await crud.set_all_muted(db, channel_cf, phone_number_id_cf, True, tenant_id=tenant_id)
            log.info("[MUTE] all set muted=true channel=%s phone_number_id=%s", channel_cf, phone_number_id_cf)
            await _send_reply_and_return_ok(remote_jid, "Ок. Я отключил автоответ для всех чатов этого номера.")
            return {"ok": True}
        if mute_cmd == "start_all":
            await crud.set_all_muted(db, channel_cf, phone_number_id_cf, False, tenant_id=tenant_id)
            log.info("[MUTE] all set muted=false channel=%s phone_number_id=%s", channel_cf, phone_number_id_cf)
            await _send_reply_and_return_ok(remote_jid, "Ок. Автоответ для всех чатов снова включён.")
            return {"ok": True}

    # AI отвечает только если tenant.ai_enabled и не chat_muted
    if tenant_id is None:
        log.info("[AI] skipped reply tenant=None reason=no_tenant")
        return {"ok": True}
    chat_muted = await crud.is_chat_muted(db, tenant_id, channel_cf, phone_number_id_cf, remote_jid)
    if not ai_enabled:
        log.info("[AI] skipped reply tenant=%s reason=tenant_disabled", tenant_id)
        return {"ok": True}
    if chat_muted:
        log.info("[AI] skipped reply tenant=%s reason=chat_muted", tenant_id)
        return {"ok": True}

    messages_for_gpt = await conversation_service.build_context_messages(db, conv.id, limit=CONTEXT_LIMIT)
    log.info("[CHATFLOW] messages loaded count=%s", len(messages_for_gpt))

    # System: номер из jid (не проси номер) + при наличии истории не повторять приветствие
    extra_system = CHATFLOW_PHONE_CONTEXT.format(phone=phone_from_jid)
    if len(messages_for_gpt) > 1:
        extra_system += "\n\n" + EXTRA_SYSTEM_CONTEXT

    response_text = ""
    function_call = None
    try:
        response_text, function_call = await openai_service.chat_with_gpt(
            messages_for_gpt, use_functions=True, extra_system_content=extra_system
        )
        log.info("[CHATFLOW] openai ok reply_len=%s function_call=%s", len(response_text or ""), bool(function_call))
    except Exception as e:
        log.error("[CHATFLOW] OpenAI error: %s", type(e).__name__, exc_info=True)

    reply = (response_text or "").strip() or "Чем могу помочь?"

    # Обработка register_lead: один активный lead на jid, телефон из jid
    if function_call and function_call.get("name") == "register_lead":
        args = function_call.get("arguments") or {}
        # Телефон всегда из jid для ChatFlow
        phone_for_lead = phone_from_jid
        if isinstance(args.get("phone"), str) and args["phone"].strip():
            phone_for_lead = args["phone"].strip()
        else:
            args = dict(args)
            args["phone"] = phone_for_lead
        try:
            owner_id = await _get_default_owner_id(db)
            if owner_id:
                bot_user = await crud.get_or_create_bot_user(db, user_id=remote_jid, owner_id=owner_id)
                active_lead = await crud.get_active_lead_by_bot_user(db, bot_user.id)
                name = (args.get("name") or "").strip() or "Клиент"
                language = (args.get("language") or "ru").strip() or "ru"
                summary = (args.get("summary") or "").strip() or "Заявка из WhatsApp"
                city = (args.get("city") or "").strip()
                object_type = (args.get("object_type") or "").strip()
                area = (args.get("area") or "").strip()
                if active_lead:
                    # Обновить существующий лид (не создавать новый)
                    active_lead.name = name
                    active_lead.phone = phone_for_lead
                    active_lead.summary = summary or active_lead.summary
                    if city:
                        active_lead.city = city
                    if object_type:
                        active_lead.object_type = object_type
                    if area:
                        active_lead.area = area
                    active_lead.language = language
                    await db.commit()
                    await db.refresh(active_lead)
                    log.info("[CHATFLOW] lead updated lead_id=%s", active_lead.id)
                else:
                    active_lead = await crud.create_lead(
                        db=db,
                        owner_id=owner_id,
                        bot_user_id=bot_user.id,
                        name=name,
                        phone=phone_for_lead,
                        summary=summary,
                        language=language,
                        city=city,
                        object_type=object_type,
                        area=area,
                    )
                    log.info("[CHATFLOW] lead created lead_id=%s", active_lead.id)
                if language == "kk":
                    reply = f"Рақмет, {name}! Сіздің өтінішіңіз қабылданды. Біздің менеджер жақын арада {phone_for_lead} нөміріне хабарласады."
                else:
                    reply = f"Спасибо, {name}! Наш менеджер свяжется с вами по номеру {phone_for_lead} в ближайшее время."
        except Exception as e:
            log.error("[CHATFLOW] register_lead error: %s", type(e).__name__, exc_info=True)

    try:
        await conversation_service.append_assistant_message(db, conv.id, reply)
    except Exception as e:
        log.warning("[CHATFLOW] append_assistant_message error: %s", type(e).__name__)

    await _send_reply_and_return_ok(remote_jid, reply)
    return {"ok": True}
