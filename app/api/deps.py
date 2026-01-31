"""
FastAPI зависимости (dependencies)
"""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.database import crud
from app.database.models import User
from app.core.security import decode_access_token

# Security scheme для JWT
security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Генератор асинхронной сессии БД
    
    Использование:
        @app.get("/endpoint")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """
    Получить текущего авторизованного пользователя
    
    Проверяет JWT токен в заголовке Authorization: Bearer <token>
    Если токен валиден - возвращает объект User
    Если нет - выбрасывает 401 Unauthorized
    
    Использование:
        @app.get("/protected")
        async def protected(current_user: User = Depends(get_current_user)):
            # current_user - авторизованный пользователь
            ...
    """
    # Извлекаем токен из заголовка
    token = credentials.credentials
    
    # Декодируем токен и получаем email
    email = decode_access_token(token)
    
    print(f"[Auth] Proverka tokena dlya email: {email}")
    
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Ищем пользователя в БД
    user = await crud.get_user_by_email(db, email=email)
    
    if user is None:
        print(f"[Auth ERROR] Polzovatel s email {email} ne nayden v BD")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    
    print(f"[Auth OK] Polzovatel nayden: ID={user.id}, Company={user.company_name}")
    return user


async def get_current_admin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Текущий пользователь должен быть админом: is_admin=True или email в ADMIN_EMAILS.
    Иначе 403 Forbidden.
    """
    from app.core.config import get_settings
    settings = get_settings()
    is_admin = getattr(current_user, "is_admin", False)
    if not is_admin and getattr(settings, "admin_emails", None):
        emails_str = settings.admin_emails.strip()
        if emails_str:
            admin_list = [e.strip().lower() for e in emails_str.split(",") if e.strip()]
            if current_user.email.lower() in admin_list:
                is_admin = True
    if not is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user
