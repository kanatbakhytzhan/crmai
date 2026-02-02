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
from app.database.models import User, Lead

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
    Smoke-test: создать тестовый комментарий к последнему лиду, прочитать комментарии, удалить тестовый.
    Возвращает ok: true если всё прошло, иначе ok: false и reason.
    Только для админов.
    """
    # Найти любой лид (самый свежий)
    result = await db.execute(select(Lead).order_by(Lead.id.desc()).limit(1))
    lead = result.scalar_one_or_none()
    if not lead:
        return {"ok": False, "reason": "no_leads"}

    comment_id = None
    try:
        # Создать тестовый комментарий
        comment = await crud.create_lead_comment(
            db,
            lead_id=lead.id,
            user_id=current_user.id,
            text="[smoke-test] diagnostic check",
        )
        comment_id = comment.id
        # Прочитать комментарии
        comments = await crud.get_lead_comments(db, lead_id=lead.id, limit=10)
        if not any(c.id == comment_id for c in comments):
            await crud.delete_lead_comment(db, comment_id)
            return {"ok": False, "reason": "comment_created_but_not_found_in_list"}
        # Удалить тестовый комментарий
        await crud.delete_lead_comment(db, comment_id)
        return {"ok": True}
    except Exception as e:
        if comment_id:
            try:
                await crud.delete_lead_comment(db, comment_id)
            except Exception:
                pass
        return {
            "ok": False,
            "reason": f"{type(e).__name__}: {str(e)[:200]}",
            "created_test_comment_id": comment_id,
        }
