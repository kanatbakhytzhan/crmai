"""Схемы для tenants, tenant_users и whatsapp_accounts (multi-tenant)."""
from pydantic import BaseModel, Field, AliasChoices
from datetime import datetime
from typing import Optional


class TenantCreate(BaseModel):
    name: str
    slug: str
    default_owner_user_id: Optional[int] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    slug: Optional[str] = None
    is_active: Optional[bool] = None
    default_owner_user_id: Optional[int] = None
    ai_enabled: Optional[bool] = None
    ai_prompt: Optional[str] = None
    webhook_key: Optional[str] = None  # UUID для POST /api/chatflow/webhook/{key}


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    default_owner_user_id: Optional[int] = None
    ai_enabled: bool = True
    ai_prompt: Optional[str] = None
    webhook_key: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AISettingsResponse(BaseModel):
    """GET /api/admin/tenants/{id}/ai-settings"""
    ai_enabled: bool
    ai_prompt: Optional[str] = None


class AISettingsUpdate(BaseModel):
    """PATCH /api/admin/tenants/{id}/ai-settings"""
    ai_enabled: Optional[bool] = None
    ai_prompt: Optional[str] = None


class MeAISettingsResponse(BaseModel):
    """GET /api/me/ai-settings"""
    tenant_id: int
    ai_enabled: bool


class MeAISettingsUpdate(BaseModel):
    """PATCH /api/me/ai-settings"""
    ai_enabled: Optional[bool] = None


class TenantUserAdd(BaseModel):
    """POST /api/admin/tenants/{id}/users — добавить пользователя по email."""
    email: str
    role: str = "member"  # manager | admin | member


class TenantUserResponse(BaseModel):
    """Пользователь tenant (для GET списка)."""
    id: int
    user_id: int
    email: str
    company_name: Optional[str] = None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class WhatsAppAccountCreate(BaseModel):
    """Привязка WhatsApp к tenant. Принимает chatflow_token или token, chatflow_instance_id или instance_id, is_active или active."""
    phone_number: str = Field("—", validation_alias=AliasChoices("phone_number", "phone"))
    phone_number_id: Optional[str] = None
    verify_token: Optional[str] = None
    waba_id: Optional[str] = None
    chatflow_token: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_token", "token"))
    chatflow_instance_id: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_instance_id", "instance_id"))
    is_active: bool = Field(True, validation_alias=AliasChoices("is_active", "active"))


class WhatsAppAccountResponse(BaseModel):
    """Ответ с сохранёнными значениями; chatflow_token не возвращается, только chatflow_token_masked."""
    id: int
    tenant_id: int
    phone_number: str
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    chatflow_token_masked: Optional[str] = None
    chatflow_instance_id: Optional[str] = None

    class Config:
        from_attributes = True


class WhatsAppAccountUpsert(BaseModel):
    """PUT /api/admin/tenants/{id}/whatsapp — сохранить/обновить привязку. Принимает token/chatflow_token, instance_id/chatflow_instance_id, active/is_active."""
    chatflow_token: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_token", "token"))
    chatflow_instance_id: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_instance_id", "instance_id"))
    phone_number: Optional[str] = Field(None, validation_alias=AliasChoices("phone_number", "phone"))
    is_active: bool = Field(True, validation_alias=AliasChoices("is_active", "active"))


class WhatsAppSaved(BaseModel):
    """Сохранённые значения привязки для ответа attach и list (id, tenant_id, phone_number, active, chatflow_instance_id, chatflow_token)."""
    id: int
    tenant_id: int
    phone_number: str
    active: bool
    chatflow_instance_id: Optional[str] = None
    chatflow_token: Optional[str] = None  # полное значение, чтобы фронт видел что сохранилось
