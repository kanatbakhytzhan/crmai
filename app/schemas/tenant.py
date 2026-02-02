"""Схемы для tenants, tenant_users и whatsapp_accounts (multi-tenant)."""
from pydantic import BaseModel
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
    """Привязка WhatsApp к tenant (Meta Cloud и/или ChatFlow). phone_number_id обязателен для Meta."""
    phone_number: str
    phone_number_id: Optional[str] = None  # для ChatFlow-only можно пусто
    verify_token: Optional[str] = None
    waba_id: Optional[str] = None
    chatflow_token: Optional[str] = None
    chatflow_instance_id: Optional[str] = None


class WhatsAppAccountResponse(BaseModel):
    id: int
    tenant_id: int
    phone_number: str
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    is_active: bool
    created_at: datetime
    chatflow_token: Optional[str] = None
    chatflow_instance_id: Optional[str] = None

    class Config:
        from_attributes = True


class WhatsAppAccountUpsert(BaseModel):
    """PUT /api/admin/tenants/{id}/whatsapp — сохранить/обновить привязку (token, instance_id, phone_number, active)."""
    chatflow_token: Optional[str] = None
    chatflow_instance_id: Optional[str] = None
    phone_number: Optional[str] = None
    is_active: bool = True
