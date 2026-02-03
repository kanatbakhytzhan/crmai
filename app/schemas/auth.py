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
    """Смена пароля пользователем (POST /api/auth/change-password)."""
    current_password: str = Field(..., description="Текущий пароль")
    new_password: str = Field(..., min_length=6, description="Новый пароль (мин. 6 символов)")
    confirm_password: str = Field(..., min_length=6, description="Повтор нового пароля")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"current_password": "old_pass_123", "new_password": "new_secure_456", "confirm_password": "new_secure_456"},
            ]
        }
    }
