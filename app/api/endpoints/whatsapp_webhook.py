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


@router.get("/webhook")
async def webhook_verify(
    request: Request,
    hub_mode: str | None = None,
    hub_verify_token: str | None = None,
    hub_challenge: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Meta verification: hub.mode, hub.verify_token, hub.challenge.
    verify_token сверяется с whatsapp_accounts.verify_token или WHATSAPP_VERIFY_TOKEN (fallback).
    """
    if not _whatsapp_enabled():
        return PlainTextResponse("disabled", status_code=404)
    if hub_mode != "subscribe" or not hub_challenge:
        return PlainTextResponse("bad request", status_code=400)
    settings = get_settings()
    expected = getattr(settings, "whatsapp_verify_token", None) or os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if expected and hub_verify_token == expected:
        return PlainTextResponse(hub_challenge)
    from sqlalchemy import select
    from app.database.models import WhatsAppAccount
    r = await db.execute(
        select(WhatsAppAccount).where(WhatsAppAccount.verify_token == hub_verify_token).where(WhatsAppAccount.is_active == True)
    )
    acc = r.scalar_one_or_none()
    if acc:
        return PlainTextResponse(hub_challenge)
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