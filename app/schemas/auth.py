"""
Pydantic схемы для авторизации (JWT)
"""
from pydantic import BaseModel
from typing import Optional


class Token(BaseModel):
    """Схема JWT токена"""
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Данные извлеченные из токена"""
    email: Optional[str] = None
