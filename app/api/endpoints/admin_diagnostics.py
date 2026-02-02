"""
Admin-only diagnostics: DB tables check и smoke-test комментариев.
Доступ только для админа (get_current_admin).
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.core.config import get_settings
from app.database import crud
from app.database.models import User, Lead, Tenant

router = APIRouter()

TABLES_TO_CHECK = [
    "tenants",
    "users",
    "leads",
    "lead_comments",
    "tenant_users",
    "conversations",
    "conversation_messages",
    "whatsapp_accounts",
]

TABLE_NOTES = {
    "lead_comments": "lead_comments missing: comments feature will fail",
    "tenant_users": "tenant_users missing: multi-user per tenant will fail",
    "conversations": "conversations missing: chat context will fail",
    "conversation_messages": "conversation_messages missing: chat context will fail",
    "whatsapp_accounts": "whatsapp_accounts missing: WhatsApp webhook will fail",
}


@router.get("/diagnostics/db")
async def diagnostics_db(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Автопроверка БД: существование таблиц.
    Возвращает tables (name -> true/false) и notes (предупреждения).
    Только для админов.
    """
    db_url = get_settings().database_url
    is_postgres = "postgresql" in db_url
    tables = {}
    notes = []

    for table_name in TABLES_TO_CHECK:
        try:
            if is_postgres:
                result = await db.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = :t"
                    ),
                    {"t": table_name},
                )
            else:
                result = await db.execute(
                    text(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :t"
                    ),
                    {"t": table_name},
                )
            exists = result.scalar_one_or_none() is not None
            tables[table_name] = exists
            if not exists and table_name in TABLE_NOTES:
                notes.append(TABLE_NOTES[table_name])
        except Exception as e:
            tables[table_name] = False
            notes.append(f"{table_name}: check failed ({type(e).__name__})")

    return {
        "ok": True,
        "tables": tables,
        "notes": notes,
    }


@router.post("/diagnostics/smoke-test")
async def diagnostics_smoke_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Smoke-test: (1) комментарий к последнему лиду; (2) whatsapp binding для первого tenant.
    Возвращает ok: true если всё прошло, иначе ok: false и reason.
    Только для админов.
    """
    # --- 1) Комментарий к лиду ---
    result = await db.execute(select(Lead).order_by(Lead.id.desc()).limit(1))
    lead = result.scalar_one_or_none()
    if not lead:
        return {"ok": False, "reason": "no_leads"}

    comment_id = None
    try:
        comment = await crud.create_lead_comment(
            db,
            lead_id=lead.id,
            user_id=current_user.id,
            text="[smoke-test] diagnostic check",
        )
        comment_id = comment.id
        comments = await crud.get_lead_comments(db, lead_id=lead.id, limit=10)
        if not any(c.id == comment_id for c in comments):
            await crud.delete_lead_comment(db, comment_id)
            return {"ok": False, "reason": "comment_created_but_not_found_in_list"}
        await crud.delete_lead_comment(db, comment_id)
    except Exception as e:
        if comment_id:
            try:
                await crud.delete_lead_comment(db, comment_id)
            except Exception:
                pass
        return {
            "ok": False,
            "reason": f"comment: {type(e).__name__}: {str(e)[:200]}",
            "created_test_comment_id": comment_id,
        }

    # --- 2) WhatsApp binding: upsert для первого tenant, затем list ---
    tenants = await crud.list_tenants(db)
    if not tenants:
        return {"ok": True}
    tenant_id = tenants[0].id
    try:
        acc = await crud.upsert_whatsapp_for_tenant(
            db,
            tenant_id=tenant_id,
            phone_number="+smoke-test",
            chatflow_token="smoke_token",
            chatflow_instance_id="smoke_instance",
            is_active=False,
        )
        accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
        if not accounts:
            return {"ok": False, "reason": "whatsapp_upsert_ok_but_list_empty"}
        if accounts[0].id != acc.id:
            return {"ok": False, "reason": "whatsapp_list_first_id_mismatch"}
    except Exception as e:
        return {
            "ok": False,
            "reason": f"whatsapp: {type(e).__name__}: {str(e)[:200]}",
        }

    # --- 3) Tenant по webhook_key (для ChatFlow webhook?key=...) ---
    t = tenants[0]
    webhook_key = getattr(t, "webhook_key", None) or ""
    if webhook_key:
        by_key = await crud.get_tenant_by_webhook_key(db, webhook_key)
        if not by_key or by_key.id != t.id:
            return {"ok": False, "reason": "tenant_by_webhook_key_mismatch"}
    return {"ok": True}


@router.post("/diagnostics/fix-leads-tenant", response_model=dict)
async def diagnostics_fix_leads_tenant(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Бэкофис: найти лиды с tenant_id IS NULL и попытаться проставить tenant_id.
    Правила: (a) conversation по remote_jid (lead.bot_user.user_id);
             (b) tenant где default_owner_user_id == lead.owner_id.
    Идемпотентно. Только для админов (JWT admin).
    Возвращает: { ok, fixed, skipped, skipped_ids, notes }.
    """
    result = await db.execute(select(Lead).where(Lead.tenant_id.is_(None)))
    leads_without_tenant = list(result.scalars().all())
    fixed = 0
    skipped_ids: list[int] = []
    notes: list[str] = []

    for lead in leads_without_tenant:
        resolved = await crud.resolve_lead_tenant_id(db, lead)
        if resolved is not None:
            lead.tenant_id = resolved
            await db.commit()
            await db.refresh(lead)
            fixed += 1
            notes.append(f"lead_id={lead.id} -> tenant_id={resolved}")
        else:
            skipped_ids.append(lead.id)
            bot_user = await crud.get_bot_user_by_id(db, lead.bot_user_id)
            remote_jid = (bot_user.user_id if bot_user else "") or ""
            notes.append(f"lead_id={lead.id} skipped (no conversation/tenant), remote_jid={remote_jid!r}")

    return {
        "ok": True,
        "fixed": fixed,
        "skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
        "notes": notes,
    }
