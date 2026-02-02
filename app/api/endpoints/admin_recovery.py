"""
Аварийное восстановление доступа админа (BuildCRM).
Endpoint работает БЕЗ логина, защищён секретным ключом из env (ADMIN_RECOVERY_KEY).
Только для восстановления is_active после случайной самоблокировки.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.config import get_settings
from app.database import crud

router = APIRouter(tags=["Admin Recovery"])


class RecoveryEnableBody(BaseModel):
    """Body для POST /api/admin/recovery/enable-user"""
    email: EmailStr


class RecoveryEnableResponse(BaseModel):
    ok: bool
    email: str
    is_active: bool


@router.post(
    "/recovery/enable-user",
    response_model=RecoveryEnableResponse,
    summary="Аварийное восстановление аккаунта (без логина)",
)
async def recovery_enable_user(
    body: RecoveryEnableBody,
    db: AsyncSession = Depends(get_db),
    x_recovery_key: str | None = Header(None, alias="X-Recovery-Key"),
):
    """
    Включить аккаунт (is_active=true) по email. Работает без Bearer token.
    Требует заголовок X-Recovery-Key с секретом из env ADMIN_RECOVERY_KEY.
    Только для аварийного восстановления после случайного отключения (is_active=false).
    is_admin не меняется.
    """
    secret = (get_settings().admin_recovery_key or "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Recovery not configured (ADMIN_RECOVERY_KEY not set)",
        )
    key = (x_recovery_key or "").strip()
    if key != secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid recovery key",
        )
    user = await crud.get_user_by_email(db, email=body.email)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    await crud.update_user(db, user.id, is_active=True)
    user = await crud.get_user_by_id(db, user.id)
    return RecoveryEnableResponse(
        ok=True,
        email=user.email,
        is_active=getattr(user, "is_active", True),
    )
