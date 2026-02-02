"""
Pydantic схемы для авторизации (JWT)
"""
from pydantic import BaseModel, Field
from typing import Optional


class Token(BaseModel):
    """Схема JWT токена"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Данные извлеченные из токена"""
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Смена пароля пользователем"""
    current_password: str
    new_password: str = Field(..., min_length=6)
    confirm_password: str = Field(..., min_length=6)
