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
    status: str  # "new", "in_progress", "done", "cancelled" — для CRM
    created_at: datetime
    last_comment: Optional[str] = None  # preview последнего комментария (до 100 символов)
    lead_number: Optional[int] = None  # CRM v2: порядковый номер лида

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def status_to_str(cls, v):
        """Enum из БД приводим к строке для API/CRM."""
        if hasattr(v, "value"):
            return v.value
        return str(v) if v is not None else "new"


class LeadCommentCreate(BaseModel):
    """Создание комментария к лиду"""
    text: str = Field(..., min_length=1)


class AIMuteUpdate(BaseModel):
    """POST /api/leads/{lead_id}/ai-mute — включить/выключить AI в чате лида."""
    muted: bool = Field(..., description="true = отключить AI в этом чате, false = включить")


class LeadCommentResponse(BaseModel):
    """Комментарий к лиду"""
    id: int
    lead_id: int
    user_id: int
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}
