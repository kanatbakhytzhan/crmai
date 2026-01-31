"""
WhatsApp webhook: verification (GET) и приём сообщений (POST).
MULTITENANT_ENABLED / WHATSAPP_ENABLED управляют включением.
"""
import os
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import PlainTextResponse

from app.api.deps import get_db
from app.core.config import get_settings
from app.database import crud
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

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
    """Первое непустое значение из request.query_params по одному из ключей (Meta: hub.mode, Swagger: hub_mode)."""
    for key in keys:
        v = request.query_params.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _mask_token(token: str) -> str:
    """Маска токена для логов: первые 3 + *** + последние 2 (без полного секрета)."""
    if not token or len(token) <= 5:
        return "***" if token else "(empty)"
    return token[:3] + "***" + token[-2:]


@router.get("/webhook")
async def webhook_verify(request: Request):
    """
    Meta verification: hub.mode / hub_mode, hub.verify_token / hub_verify_token, hub.challenge / hub_challenge.
    Токен проверяется только по env WHATSAPP_VERIFY_TOKEN. БД не используется.
    """
    if not _whatsapp_enabled():
        return PlainTextResponse("disabled", status_code=404)

    mode = _qp(request, "hub.mode", "hub_mode")
    token = _qp(request, "hub.verify_token", "hub_verify_token")
    challenge = _qp(request, "hub.challenge", "hub_challenge")

    if mode != "subscribe":
        return PlainTextResponse("bad request", status_code=400)
    if not token or not challenge:
        return PlainTextResponse("bad request", status_code=400)

    env_token = (getattr(get_settings(), "whatsapp_verify_token", None) or os.environ.get("WHATSAPP_VERIFY_TOKEN"))
    env_token = (env_token or "").strip()

    if env_token and token == env_token:
        print(f"[WA] verify ok token_mask={_mask_token(token)}")
        return PlainTextResponse(challenge, status_code=200)
    print(f"[WA] verify forbidden token_mask={_mask_token(token)}")
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
            messages = value.get("messages") or []
            for msg in messages:
                text = ""
                if msg.get("type") == "text":
                    text = (msg.get("text") or {}).get("body") or ""
                from_wa_id = msg.get("from")
                lead = await crud.create_lead_from_whatsapp(db, tenant_id=tenant_id, message_text=text, from_wa_id=from_wa_id)
                if lead:
                    print(f"[WA] webhook received phone_number_id={phone_number_id} tenant={tenant_id} created lead id={lead.id}")
                else:
                    print(f"[WA] webhook received phone_number_id={phone_number_id} tenant={tenant_id} created lead id=(failed)")
    return {"ok": True}