"""
Pydantic схемы для админки пользователей (BuildCRM PWA)
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Optional


class UserAdminList(BaseModel):
    """Пользователь в списке (без пароля)"""
    id: int
    email: str
    company_name: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserAdminCreate(BaseModel):
    """Создание пользователя (админ)"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    company_name: Optional[str] = None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"email": "user@example.com", "password": "secret123", "company_name": "My Company"}
            ]
        }
    }


class UserAdminUpdate(BaseModel):
    """Обновление пользователя (админ)"""
    is_active: Optional[bool] = None
    company_name: Optional[str] = None
    is_admin: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    """Сброс пароля"""
    password: str = Field(..., min_length=6)
