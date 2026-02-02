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


@router.get("/ai-settings", response_model=MeAISettingsResponse)
async def get_me_ai_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Настройки AI для tenant текущего пользователя.
    Tenant: первый из tenant_users, иначе tenant где default_owner_user_id == current_user.id.
    """
    tenant = await crud.get_tenant_for_me(db, current_user.id)
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
    tenant = await crud.get_tenant_for_me(db, current_user.id)
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
