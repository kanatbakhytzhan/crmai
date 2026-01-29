"""
Pydantic схемы для Lead (заявка)
"""
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional, Literal
from enum import Enum


class LeadStatusEnum(str, Enum):
    """Статусы заявки для API"""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class LeadCreate(BaseModel):
    """Схема для создания заявки"""
    bot_user_id: int
    name: str
    phone: str
    city: Optional[str] = None
    object_type: Optional[str] = None
    area: Optional[str] = None
    summary: Optional[str] = None
    language: str = "ru"


class LeadStatusUpdate(BaseModel):
    """Схема для обновления статуса заявки"""
    status: LeadStatusEnum = Field(..., description="Новый статус заявки")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"status": "in_progress"},
                {"status": "success"},
                {"status": "failed"}
            ]
        }
    }


class LeadResponse(BaseModel):
    """Схема ответа с данными заявки"""
    id: int
    owner_id: int
    bot_user_id: int
    name: str
    phone: str
    city: Optional[str] = None
    object_type: Optional[str] = None
    area: Optional[str] = None
    summary: Optional[str] = None
    language: str
    status: str  # Изменено на str для совместимости
    created_at: datetime
    
    model_config = {"from_attributes": True}
