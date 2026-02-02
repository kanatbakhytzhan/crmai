"""
API эндпоинты админки пользователей (BuildCRM PWA)
Доступ только для админа (is_admin или ADMIN_EMAILS).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.database import crud
from app.database.models import User
from app.schemas.admin_users import (
    UserAdminList,
    UserAdminCreate,
    UserAdminUpdate,
)

router = APIRouter()


def _user_to_admin_list(user: User) -> UserAdminList:
    """ORM User -> UserAdminList (устойчиво к отсутствию is_admin в БД)."""
    return UserAdminList(
        id=user.id,
        email=user.email,
        company_name=user.company_name,
        is_active=user.is_active,
        is_admin=getattr(user, "is_admin", False),
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.get("/users", response_model=dict)
async def list_users(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Список пользователей (без паролей).
    Требует Bearer token и права админа.
    """
    users = await crud.get_all_users(db)
    items = [_user_to_admin_list(u) for u in users]
    return {"users": items, "total": len(items)}


@router.post("/users", response_model=UserAdminList, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserAdminCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Создать пользователя (email, password, company_name).
    is_active=True, is_admin=False по умолчанию.
    409 если email уже существует.
    """
    existing = await crud.get_user_by_email(db, email=body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists"
        )
    company_name = body.company_name or body.email.split("@")[0]
    user = await crud.create_user(
        db,
        email=body.email,
        password=body.password,
        company_name=company_name,
    )
    return _user_to_admin_list(user)


@router.patch("/users/{user_id}", response_model=UserAdminList)
async def update_user(
  user_id: int,
  body: UserAdminUpdate,
  db: AsyncSession = Depends(get_db),
  current_user: User = Depends(get_current_admin),
):
    """
    Обновить пользователя (is_active, company_name, is_admin).
    404 если пользователь не найден.
    """
    user = await crud.update_user(
        db,
        user_id,
        is_active=body.is_active,
        company_name=body.company_name,
        is_admin=body.is_admin,
    )
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return _user_to_admin_list(user)


def _generate_temporary_password(length: int = 12) -> str:
    """Генерация временного пароля (буквы + цифры)."""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Сброс пароля пользователя админом.
    Генерирует временный пароль (10–12 символов), сохраняет в БД, возвращает в JSON.
    Email/SMS не отправляется (MVP).
    """
    user = await crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    temporary_password = _generate_temporary_password(12)
    await crud.set_user_password(db, user_id, temporary_password)
    return {"ok": True, "temporary_password": temporary_password}
