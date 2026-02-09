"""
Эндпоинты для текущего пользователя (не админ): /api/me/...
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.database import crud
from app.database.models import User
from app.schemas.tenant import MeAISettingsResponse, MeAISettingsUpdate

router = APIRouter()


@router.get("", response_model=dict, summary="Информация о текущем пользователе")
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Возвращает информацию о текущем пользователе: id, email, company_name, is_admin, tenant_id, role.
    """
    from sqlalchemy import text
    from fastapi.responses import JSONResponse
    
    try:
        # Get tenant using raw SQL to avoid ORM column issues
        tenant_id = None
        role = None
        
        # First check tenant_users
        result = await db.execute(text(
            "SELECT tenant_id FROM tenant_users WHERE user_id = :uid LIMIT 1"
        ), {"uid": current_user.id})
        row = result.fetchone()
        if row:
            tenant_id = row[0]
        
        # Fallback: check default_owner_user_id
        if not tenant_id:
            result = await db.execute(text(
                "SELECT id FROM tenants WHERE default_owner_user_id = :uid AND is_active = 1 LIMIT 1"
            ), {"uid": current_user.id})
            row = result.fetchone()
            if row:
                tenant_id = row[0]
        
        # Get role if we have tenant_id
        if tenant_id:
            result = await db.execute(text(
                "SELECT role FROM tenant_users WHERE tenant_id = :tid AND user_id = :uid"
            ), {"tid": tenant_id, "uid": current_user.id})
            row = result.fetchone()
            if row:
                role = (row[0] or "").strip().lower() or "manager"
                if role == "member":
                    role = "manager"
            else:
                role = "manager"
        
        return {
            "id": current_user.id,
            "email": current_user.email,
            "company_name": getattr(current_user, "company_name", None),
            "is_admin": getattr(current_user, "is_admin", False),
            "tenant_id": tenant_id,
            "role": role,
        }
    except Exception as e:
        import traceback
        print(f"[ERROR] get_me failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Failed to get user info: {type(e).__name__}"})


@router.get("/role", response_model=dict, summary="Роль и tenant текущего пользователя")
async def get_me_role(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Возвращает **tenant_id** и **role** (owner | rop | manager) для текущего пользователя.
    Нужен JWT. Если пользователь не привязан к tenant — tenant_id и role будут null.
    """
    tenant = await crud.get_tenant_for_me(db, current_user.id)
    if not tenant:
        return {"tenant_id": None, "role": None}
    role = await crud.get_tenant_user_role(db, tenant.id, current_user.id)
    return {"tenant_id": tenant.id, "role": role or "manager"}


@router.get("/ai-settings", response_model=MeAISettingsResponse)
async def get_me_ai_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Настройки AI для tenant текущего пользователя.
    Tenant: первый из tenant_users, иначе tenant где default_owner_user_id == current_user.id.
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        tenant = await crud.get_tenant_for_me(db, current_user.id)
    except Exception as e:
        log.error("[ME] get_ai_settings error: %s", type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        )
    return MeAISettingsResponse(
        tenant_id=tenant.id,
        ai_enabled=getattr(tenant, "ai_enabled", True),
    )


@router.patch("/ai-settings", response_model=MeAISettingsResponse)
async def patch_me_ai_settings(
    body: MeAISettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Обновить ai_enabled для tenant текущего пользователя.
    """
    import logging
    log = logging.getLogger(__name__)
    try:
        tenant = await crud.get_tenant_for_me(db, current_user.id)
    except Exception as e:
        log.error("[ME] patch_ai_settings error: %s", type(e).__name__, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        )
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant_not_found",
        )
    updated = await crud.update_tenant(db, tenant.id, ai_enabled=body.ai_enabled)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant_not_found")
    return MeAISettingsResponse(
        tenant_id=updated.id,
        ai_enabled=getattr(updated, "ai_enabled", True),
    )
