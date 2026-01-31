"""
WhatsApp webhook: verification (GET) и приём сообщений (POST).
MULTITENANT_ENABLED / WHATSAPP_ENABLED управляют включением.
Chat history: per (tenant_id + wa_from), last 20 messages as context for AI.
"""
import logging
import os
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import get_db
from app.core.config import get_settings
from app.database import crud
from app.services import openai_service, conversation_service, whatsapp_cloud_api
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()
log = logging.getLogger(__name__)

# Пример тела для Swagger /docs (Meta WhatsApp webhook payload)
WHATSAPP_WEBHOOK_BODY_EXAMPLE = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "1",
            "changes": [
                {
                    "value": {
                        "metadata": {"phone_number_id": "111111111111111"},
                        "messages": [
                            {
                                "from": "77001234567",
                                "type": "text",
                                "text": {"body": "Тест лид из WhatsApp"},
                            }
                        ],
                    }
                }
            ],
        }
    ],
}


def _whatsapp_enabled() -> bool:
    return get_settings().whatsapp_enabled.upper() == "TRUE"


def _qp(request: Request, *keys: str) -> str | None:
    """Первое непустое значение из request.query_params (hub.mode / hub_mode и т.д.)."""
    for key in keys:
        v = request.query_params.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


@router.get("/webhook")
async def webhook_verify(request: Request):
    """
    Meta verification: читает hub_mode, hub_verify_token, hub_challenge из query
    (поддержка hub.mode/hub_mode, hub.verify_token/hub_verify_token, hub.challenge/hub_challenge).
    Только env WHATSAPP_VERIFY_TOKEN, БД не используется.
    """
    if not _whatsapp_enabled():
        return PlainTextResponse("disabled", status_code=404)

    mode = _qp(request, "hub.mode", "hub_mode")
    token = _qp(request, "hub.verify_token", "hub_verify_token")
    challenge = _qp(request, "hub.challenge", "hub_challenge")
    env_token = (getattr(get_settings(), "whatsapp_verify_token", None) or os.environ.get("WHATSAPP_VERIFY_TOKEN")) or ""
    env_token = env_token.strip()

    if mode == "subscribe" and token and challenge and env_token and token == env_token:
        log.info("WA verify ok")
        return PlainTextResponse(challenge, status_code=200)
    log.info("WA verify forbidden")
    return PlainTextResponse("forbidden", status_code=403)


@router.post("/webhook")
async def webhook_post(
    payload: dict = Body(..., example=WHATSAPP_WEBHOOK_BODY_EXAMPLE),
    db: AsyncSession = Depends(get_db),
):
    """
    Принять payload Meta. Достать phone_number_id из entry[0].changes[0].value.metadata.phone_number_id.
    Найти tenant по phone_number_id, создать lead с tenant_id и текстом сообщения.
    """
    if not _whatsapp_enabled():
        return {"ok": True}
    body = payload
    entries = body.get("entry") or []
    for entry in entries:
        changes = entry.get("changes") or []
        for change in changes:
            value = change.get("value") or {}
            metadata = value.get("metadata") or {}
            phone_number_id = metadata.get("phone_number_id")
            if not phone_number_id:
                continue
            acc = await crud.get_whatsapp_account_by_phone_number_id(db, str(phone_number_id))
            if not acc:
                print(f"[WA] webhook received phone_number_id={phone_number_id} tenant=not_found (no lead created)")
                continue
            tenant_id = acc.tenant_id
            phone_number_id_str = str(phone_number_id)
            messages_list = value.get("messages") or []
            for msg in messages_list:
                text = ""
                if msg.get("type") == "text":
                    text = (msg.get("text") or {}).get("body") or ""
                from_wa_id = msg.get("from") or ""
                lead = await crud.create_lead_from_whatsapp(db, tenant_id=tenant_id, message_text=text, from_wa_id=from_wa_id)
                if lead:
                    log.info(f"[WA] webhook received phone_number_id={phone_number_id} tenant={tenant_id} created lead id={lead.id}")
                else:
                    log.info(f"[WA] webhook received phone_number_id={phone_number_id} tenant={tenant_id} created lead id=(failed)")

                conv = await conversation_service.get_or_create_conversation(
                    db, tenant_id=tenant_id, channel="whatsapp", external_id=from_wa_id, phone_number_id=phone_number_id_str
                )
                await conversation_service.append_user_message(db, conv.id, text, raw_json=msg)
                log.info(f"[WA][CHAT] conv_id={conv.id} tenant_id={tenant_id} from={from_wa_id} stored user msg")

                messages_for_gpt = await conversation_service.build_context_messages(db, conv.id, limit=20)
                log.info(f"[WA][CHAT] loaded {len(messages_for_gpt)} context messages")

                assistant_reply = ""
                try:
                    response_text, function_call = await openai_service.chat_with_gpt(messages_for_gpt, use_functions=True)
                    assistant_reply = response_text or ""
                    if function_call and function_call.get("name") == "register_lead":
                        assistant_reply = "[Lead registered]"
                except Exception as e:
                    log.warning(f"[WA][CHAT] AI error: {type(e).__name__}: {e}")
                if assistant_reply:
                    await conversation_service.append_assistant_message(db, conv.id, assistant_reply)
                    log.info("[WA][CHAT] stored assistant msg")
                    send_result = await whatsapp_cloud_api.send_text_message(
                        phone_number_id_str, from_wa_id, assistant_reply
                    )
                    if send_result.get("skipped"):
                        log.info("[WA][SEND] skipped %s", send_result.get("reason", "unknown"))
                    elif send_result.get("ok"):
                        log.info("[WA][SEND] ok message_id=%s", send_result.get("message_id") or "—")
                    else:
                        log.warning("[WA][SEND] failed error=%s", send_result.get("error", "unknown"))
    return {"ok": True}