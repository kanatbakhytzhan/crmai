"""Схемы для tenants и whatsapp_accounts (multi-tenant)."""
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


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    default_owner_user_id: Optional[int] = None
    ai_enabled: bool = True
    ai_prompt: Optional[str] = None
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


class WhatsAppAccountCreate(BaseModel):
    phone_number: str
    phone_number_id: str
    verify_token: Optional[str] = None
    waba_id: Optional[str] = None


class WhatsAppAccountResponse(BaseModel):
    id: int
    tenant_id: int
    phone_number: str
    phone_number_id: str
    waba_id: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
