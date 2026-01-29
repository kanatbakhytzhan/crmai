"""
Pydantic схемы для User (владелец аккаунта)
"""
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class UserCreate(BaseModel):
    """Схема для регистрации нового пользователя"""
    email: EmailStr
    password: str = Field(..., min_length=6)
    company_name: str = Field(..., min_length=2)


class UserLogin(BaseModel):
    """Схема для логина"""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """Схема ответа с данными пользователя"""
    id: int
    email: str
    company_name: str
    is_active: bool
    created_at: datetime
    
    model_config = {"from_attributes": True}
