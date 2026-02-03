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
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.database import crud
from app.services import chatflow_client, conversation_service, openai_service
from app.services.events_bus import emit as events_emit

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


def _normalize_command_text(text: str) -> str:
    """Убрать пробелы/переносы, нижний регистр. Для надёжного /stop, /start."""
    if not text:
        return ""
    return (text.replace("\n", " ").replace("\r", " ").strip().lower() or "")


def _is_stop_command(text_normalized: str) -> bool:
    return (text_normalized or "").strip() in ("/stop", "stop")


def _is_start_command(text_normalized: str) -> bool:
    return (text_normalized or "").strip() in ("/start", "start")


def _parse_mute_command(text: str) -> str | None:
    """
    Команды: /stop, /start, /stop all, /start all (регистр не важен, пробелы схлопнуть).
    Возвращает: "stop" | "start" | "stop_all" | "start_all" | None.
    """
    raw = _normalize_command_text(text or "")
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
    """Первый активный tenant для ChatFlow (fallback)."""
    tenants = await crud.list_tenants(db, active_only=True)
    return tenants[0] if tenants else None


async def _resolve_tenant_from_payload(db: AsyncSession, data: dict[str, Any]):
    """Return Tenant or None."""
    """Определить tenant по instance_id или client_id в payload (chatflow_instance_id в whatsapp_accounts)."""
    instance_id = (data.get("instance_id") or data.get("client_id") or "").strip()
    if not instance_id:
        meta = data.get("metadata") or {}
        if isinstance(meta, dict):
            instance_id = (meta.get("instance_id") or meta.get("instanceId") or meta.get("client_id") or "").strip()
    if not instance_id:
        return None
    acc = await crud.get_whatsapp_account_by_chatflow_instance_id(db, instance_id)
    if not acc:
        return None
    return await crud.get_tenant_by_id(db, acc.tenant_id)


async def _resolve_tenant(db: AsyncSession, data: dict[str, Any], resolved_tenant: Any = None):
    """Tenant только по привязке: переданный resolved_tenant ИЛИ по instance_id/client_id в payload. Без fallback на первый tenant."""
    if resolved_tenant is not None:
        return resolved_tenant
    return await _resolve_tenant_from_payload(db, data)


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
async def chatflow_webhook_get(key: str | None = None):
    """ChatFlow webhook GET — health. Опционально ?key=... для проверки привязки tenant."""
    return {"ok": True}


@router.get("/ping")
async def chatflow_ping():
    """Быстрая проверка деплоя ChatFlow."""
    return {"ok": True, "pong": True}


async def _process_webhook(db: AsyncSession, data: dict[str, Any], resolved_tenant: Any = None) -> dict:
    """
    Общая логика обработки webhook: парсинг, дедуп, команды, контекст, LLM, ответ.
    resolved_tenant: если задан, используется этот tenant; иначе — по instance_id в payload или первый активный.
    """
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

    # A) Tenant только по привязке (resolved_tenant или instance_id в payload). Без fallback.
    tenant = await _resolve_tenant(db, data, resolved_tenant)
    if not tenant:
        log.warning("[AI] SKIP tenant not found for chatflow instance")
        return {"ok": True}
    tenant_id = tenant.id
    log.info("[CHATFLOW] tenant_id=%s remote_jid=%s msg_id=%s", tenant_id, remote_jid, msg_id)

    # A) WhatsApp attach активен и заполнены критичные поля (token OR instance_id)
    acc = await crud.get_active_chatflow_account_for_tenant(db, tenant_id)
    if not acc:
        log.warning("[AI] SKIP whatsapp not attached/inactive")
        return {"ok": True}

    # Get or create conversation (channel=chatflow, external_id=remote_jid)
    try:
        conv = await conversation_service.get_or_create_conversation(
            db, tenant_id=tenant_id, channel="chatflow", external_id=remote_jid, phone_number_id=""
        )
    except Exception as e:
        log.error("[CHATFLOW] get_or_create_conversation error: %s", type(e).__name__, exc_info=True)
        return {"ok": True}

    text_norm = _normalize_command_text(user_text or "")
    jid_safe = remote_jid[-4:] if len(remote_jid) >= 4 else "****"

    # B) /stop и /start — только по remoteJid (chat_ai_states). Кто бы ни писал — один критерий: remoteJid.
    if _is_stop_command(text_norm):
        await crud.set_chat_ai_state(db, tenant_id, remote_jid, False)
        log.info("[AI] command stop jid=...%s tenant_id=%s", jid_safe, tenant_id)
        await _send_reply_and_return_ok(remote_jid, "Ок ✅ AI в этом чате выключен. Чтобы включить обратно — /start")
        return {"ok": True}
    if _is_start_command(text_norm):
        await crud.set_chat_ai_state(db, tenant_id, remote_jid, True)
        log.info("[AI] chat resumed jid=...%s tenant_id=%s", jid_safe, tenant_id)
        await _send_reply_and_return_ok(remote_jid, "Ок ✅ AI снова включён в этом чате.")
        return {"ok": True}

    # Остальные команды (stop all / start all) и обычные сообщения (tenant уже определён выше)
    ai_enabled = getattr(tenant, "ai_enabled", True) if tenant else True
    channel_cf = "chatflow"
    phone_number_id_cf = ""

    mute_cmd = _parse_mute_command(user_text or "")
    if mute_cmd == "stop_all" and tenant_id is not None:
        await crud.set_all_muted(db, channel_cf, phone_number_id_cf, True, tenant_id=tenant_id)
        await _send_reply_and_return_ok(remote_jid, "Ок. Я отключил автоответ для всех чатов этого номера.")
        return {"ok": True}
    if mute_cmd == "start_all" and tenant_id is not None:
        await crud.set_all_muted(db, channel_cf, phone_number_id_cf, False, tenant_id=tenant_id)
        await _send_reply_and_return_ok(remote_jid, "Ок. Автоответ для всех чатов снова включён.")
        return {"ok": True}

    # Сохранить входящее сообщение
    try:
        await conversation_service.append_user_message(
            db, conv.id, user_text, raw_json=data, external_message_id=msg_id or None
        )
    except Exception as e:
        log.error("[CHATFLOW] append_user_message error: %s", type(e).__name__, exc_info=True)
        return {"ok": True}

    phone_from_jid = remote_jid.split("@")[0] if "@" in remote_jid else remote_jid
    normalized_in_message = _normalize_phone(user_text)

    # C) Сообщение — только номер телефона (10–15 цифр, допустимы пробелы/+-/скобки): сохранить в lead, ответить один раз, НЕ сбрасывать контекст.
    _phone_only_re = re.compile(r"^[\d\s\-+()]+$")
    _stripped = (user_text or "").strip()
    if normalized_in_message and _phone_only_re.match(_stripped) and len(re.sub(r"\D", "", _stripped)) >= 10:
        try:
            owner_id = await _get_default_owner_id(db)
            if owner_id:
                bot_user = await crud.get_or_create_bot_user(db, user_id=remote_jid, owner_id=owner_id)
                active_lead = await crud.get_active_lead_by_bot_user(db, bot_user.id)
                if active_lead:
                    await crud.update_lead_phone(
                        db, active_lead.id, normalized_in_message, phone_from_message=normalized_in_message
                    )
                    log.info("[CHATFLOW] lead phone from message lead_id=%s phone=%s", active_lead.id, normalized_in_message)
                else:
                    active_lead = await crud.create_lead(
                        db=db, owner_id=owner_id, bot_user_id=bot_user.id,
                        name="Клиент", phone=normalized_in_message, summary="Номер из чата", language="ru",
                        tenant_id=tenant_id,
                    )
                    await crud.update_lead_phone(
                        db, active_lead.id, normalized_in_message, phone_from_message=normalized_in_message
                    )
                    log.info("[CHATFLOW] lead created from phone message lead_id=%s", active_lead.id)
                    try:
                        await events_emit("lead_created", {"lead_id": active_lead.id, "tenant_id": tenant_id})
                    except Exception:
                        pass
        except Exception as e:
            log.warning("[CHATFLOW] phone-from-message: %s", type(e).__name__)
        reply_phone = "Спасибо! Номер записал ✅"
        try:
            await conversation_service.append_assistant_message(db, conv.id, reply_phone)
        except Exception as e:
            log.warning("[CHATFLOW] append_assistant_message: %s", type(e).__name__)
        await _send_reply_and_return_ok(remote_jid, reply_phone)
        return {"ok": True}

    # Обычное обновление номера в лиде (если в тексте есть номер, но не только номер)
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

    # AI отвечает только если tenant.ai_enabled и chat_ai_state для этого чата (remoteJid) включён
    chat_ai_enabled = await crud.get_chat_ai_state(db, tenant_id, remote_jid)
    log.info("[CHATFLOW] tenant_id=%s remoteJid=...%s msg_id=%s ai_enabled_global=%s ai_muted_in_chat=%s", tenant_id, jid_safe, msg_id, ai_enabled, not chat_ai_enabled)
    if not ai_enabled:
        log.info("[AI] skipped reply tenant=%s reason=tenant_disabled", tenant_id)
        return {"ok": True}
    if not chat_ai_enabled:
        log.info("[AI] chat paused (chat_ai_state) jid=...%s tenant_id=%s", jid_safe, tenant_id)
        return {"ok": True}

    messages_for_gpt = await conversation_service.build_context_messages(db, conv.id, limit=CONTEXT_LIMIT)
    log.info("[CHATFLOW] messages loaded count=%s", len(messages_for_gpt))

    # D) tenant.ai_prompt из БД (не из старого объекта)
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    system_override = (getattr(tenant, "ai_prompt", None) or "").strip() or None
    log.info("[GPT] tenant_id=%s use_tenant_prompt=%s prompt_len=%s", tenant_id, bool(system_override), len(system_override or ""))

    # System: номер из jid (не проси номер) + при наличии истории не повторять приветствие
    extra_system = CHATFLOW_PHONE_CONTEXT.format(phone=phone_from_jid)
    if len(messages_for_gpt) > 1:
        extra_system += "\n\n" + EXTRA_SYSTEM_CONTEXT

    response_text = ""
    function_call = None
    try:
        response_text, function_call = await openai_service.chat_with_gpt(
            messages_for_gpt, use_functions=True, extra_system_content=extra_system, system_override=system_override
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
                    try:
                        await events_emit("lead_updated", {"lead_id": active_lead.id, "tenant_id": tenant_id})
                    except Exception:
                        pass
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
                        tenant_id=tenant_id,
                    )
                    log.info("[CHATFLOW] lead created lead_id=%s", active_lead.id)
                    try:
                        await events_emit("lead_created", {"lead_id": active_lead.id, "tenant_id": tenant_id})
                    except Exception:
                        pass
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


@router.post("/webhook")
async def chatflow_webhook_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: str | None = None,
):
    """
    ChatFlow webhook: tenant по query ?key=webhook_key.
    Если key отсутствует или tenant не найден — возвращаем {"ok": true} и НИЧЕГО не отправляем в WhatsApp.
    Если tenant найден — используем tenant.ai_enabled, tenant.ai_prompt, контекст по jid.
    """
    body = await request.body()
    data = None
    try:
        data = json.loads(body) if body else None
    except Exception as e:
        log.warning("[CHATFLOW] JSON parse error: %s", repr(e))
    if data is None or not isinstance(data, dict):
        return {"ok": True}
    key_present = bool((key or "").strip())
    if not key_present:
        log.info("[CHATFLOW] no key in query, skip reply")
        return {"ok": True}
    tenant = await crud.get_tenant_by_webhook_key(db, (key or "").strip())
    if not tenant:
        log.warning("[CHATFLOW] tenant not found for key=..., skip reply")
        return {"ok": True}
    return await _process_webhook(db, data, resolved_tenant=tenant)


@router.post("/webhook/{tenant_key}")
async def chatflow_webhook_post_by_key(
    tenant_key: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Webhook с привязкой к tenant по webhook_key (UUID в tenants.webhook_key).
    Используйте этот URL в ChatFlow, если instance_id в payload не привязан к tenant.
    """
    body = await request.body()
    data = None
    try:
        data = json.loads(body) if body else None
    except Exception as e:
        log.warning("[CHATFLOW] JSON parse error: %s", repr(e))
    if data is None or not isinstance(data, dict):
        return {"ok": True}
    tenant = await crud.get_tenant_by_webhook_key(db, tenant_key)
    if not tenant:
        raise HTTPException(status_code=404, detail="tenant_not_found")
    return await _process_webhook(db, data, resolved_tenant=tenant)
