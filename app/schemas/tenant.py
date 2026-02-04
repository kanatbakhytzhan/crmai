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
    # Universal Admin Console:
    whatsapp_source: Optional[str] = None  # chatflow | amomarket
    ai_enabled_global: Optional[bool] = None
    ai_after_lead_submitted_behavior: Optional[str] = None


class TenantResponse(BaseModel):
    id: int
    name: str
    slug: str
    is_active: bool
    default_owner_user_id: Optional[int] = None
    ai_enabled: bool = True
    ai_prompt: Optional[str] = None
    webhook_key: Optional[str] = None
    webhook_url: Optional[str] = None  # вычисляемое: BASE_URL + /api/chatflow/webhook?key= + webhook_key
    whatsapp_source: str = "chatflow"
    ai_enabled_global: bool = True
    ai_after_lead_submitted_behavior: Optional[str] = "polite_close"
    created_at: datetime

    class Config:
        from_attributes = True


# ========== Universal Admin Console: Tenant Settings ==========

class ChatFlowBindingSnapshot(BaseModel):
    """Snapshot of ChatFlow binding for tenant settings response."""
    binding_exists: bool = False
    is_active: bool = False
    accounts_count: int = 0
    phone_number: Optional[str] = None
    chatflow_instance_id: Optional[str] = None
    chatflow_token_masked: Optional[str] = None


class AmoCRMSnapshot(BaseModel):
    """Snapshot of AmoCRM integration status for tenant settings response."""
    connected: bool = False
    base_domain: Optional[str] = None
    expires_at: Optional[str] = None  # ISO string or null


class TenantSettingsBlock(BaseModel):
    """Settings block inside TenantSettingsResponse."""
    whatsapp_source: str = "chatflow"
    ai_enabled_global: bool = True
    ai_prompt: str = ""  # Never null - empty string if not set
    ai_prompt_len: int = 0
    ai_after_lead_submitted_behavior: str = "polite_close"
    amocrm_base_domain: Optional[str] = None


class MappingsSnapshot(BaseModel):
    """Mappings counts for tenant settings response."""
    pipeline_count: int = 0
    field_count: int = 0


class TenantSettingsResponse(BaseModel):
    """
    GET /api/admin/tenants/{id}/settings - comprehensive response with all settings and snapshots.
    ALWAYS returns complete structure with defaults - never missing keys.
    """
    ok: bool = True
    tenant_id: int = 0
    tenant_name: str = ""
    settings: TenantSettingsBlock = Field(default_factory=TenantSettingsBlock)
    whatsapp: ChatFlowBindingSnapshot = Field(default_factory=ChatFlowBindingSnapshot)
    amocrm: AmoCRMSnapshot = Field(default_factory=AmoCRMSnapshot)
    mappings: MappingsSnapshot = Field(default_factory=MappingsSnapshot)


class TenantSettingsUpdate(BaseModel):
    """PATCH /api/admin/tenants/{id}/settings"""
    whatsapp_source: Optional[str] = None
    ai_enabled_global: Optional[bool] = None
    ai_prompt: Optional[str] = None
    ai_after_lead_submitted_behavior: Optional[str] = None
    amocrm_base_domain: Optional[str] = None


class TenantSettingsErrorResponse(BaseModel):
    """Error response for /settings endpoint."""
    ok: bool = False
    detail: str = "Unknown error"


# ========== Universal Admin Console: AmoCRM ==========

class AmoCRMAuthUrlResponse(BaseModel):
    """Response for GET /api/admin/tenants/{id}/amocrm/auth-url"""
    ok: bool = True
    auth_url: Optional[str] = None
    base_domain: Optional[str] = None
    detail: Optional[str] = None  # Error message if ok=False


class AmoCRMCallbackBody(BaseModel):
    code: str
    base_domain: str  # example.amocrm.ru


class AmoCRMStatusResponse(BaseModel):
    is_active: bool = False
    base_domain: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    connected: bool = False


# ========== Universal Admin Console: Pipeline Mappings ==========

class PipelineMappingItem(BaseModel):
    stage_key: str
    stage_id: Optional[str] = None
    pipeline_id: Optional[str] = None
    is_active: bool = True


class PipelineMappingResponse(BaseModel):
    id: int
    tenant_id: int
    provider: str
    pipeline_id: Optional[str] = None
    stage_key: str
    stage_id: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class PipelineMappingBulkUpdate(BaseModel):
    mappings: list[PipelineMappingItem]


# ========== Universal Admin Console: Field Mappings ==========

class FieldMappingItem(BaseModel):
    field_key: str
    amo_field_id: Optional[str] = None
    entity_type: str = "lead"  # lead | contact
    is_active: bool = True


class FieldMappingResponse(BaseModel):
    id: int
    tenant_id: int
    provider: str
    field_key: str
    amo_field_id: Optional[str] = None
    entity_type: str
    is_active: bool

    class Config:
        from_attributes = True


class FieldMappingBulkUpdate(BaseModel):
    mappings: list[FieldMappingItem]


# ========== Universal Admin Console: Mute from Lead ==========

class LeadMuteBody(BaseModel):
    muted: bool


class LeadMuteResponse(BaseModel):
    ok: bool
    muted: Optional[bool] = None
    error: Optional[str] = None
    channel: Optional[str] = None
    external_id: Optional[str] = None


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
    """POST /api/admin/tenants/{id}/users — добавить пользователя по email. Admin/owner/rop."""
    email: str = Field(..., description="Email пользователя (создаётся, если нет в системе)")
    role: str = Field("member", description="owner | rop | manager")
    parent_user_id: Optional[int] = Field(None, description="Для manager: user_id ROP")
    is_active: Optional[bool] = True

    model_config = {
        "json_schema_extra": {
            "examples": [{"email": "manager@company.com", "role": "manager", "parent_user_id": 2}]
        }
    }


class TenantUserPatch(BaseModel):
    """PATCH /api/admin/tenants/users/{tenant_user_id}."""
    role: Optional[str] = None
    parent_user_id: Optional[int] = None
    is_active: Optional[bool] = None


class TenantUserResponse(BaseModel):
    """Пользователь tenant (для GET списка). CRM v2.5: parent_user_id, is_active."""
    id: int
    user_id: int
    email: str
    company_name: Optional[str] = None
    role: str
    parent_user_id: Optional[int] = None
    is_active: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class WhatsAppAccountCreate(BaseModel):
    """Привязка WhatsApp/ChatFlow к tenant. POST /api/admin/tenants/{id}/whatsapp."""
    phone_number: str = Field("—", validation_alias=AliasChoices("phone_number", "phone"))
    phone_number_id: Optional[str] = None
    verify_token: Optional[str] = None
    waba_id: Optional[str] = None
    chatflow_token: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_token", "token"), description="Токен ChatFlow")
    chatflow_instance_id: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_instance_id", "instance_id"), description="Instance ID из ChatFlow")
    is_active: bool = Field(True, validation_alias=AliasChoices("is_active", "active"))

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"phone_number": "+77001234567", "chatflow_token": "your_chatflow_token", "chatflow_instance_id": "instance_abc", "is_active": True}
            ]
        }
    }


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
    """PUT /api/admin/tenants/{id}/whatsapp — сохранить/обновить привязку."""
    chatflow_token: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_token", "token"))
    chatflow_instance_id: Optional[str] = Field(None, validation_alias=AliasChoices("chatflow_instance_id", "instance_id"))
    phone_number: Optional[str] = Field(None, validation_alias=AliasChoices("phone_number", "phone"))
    is_active: bool = Field(True, validation_alias=AliasChoices("is_active", "active"))

    model_config = {
        "json_schema_extra": {
            "examples": [{"chatflow_token": "xxx", "chatflow_instance_id": "instance_123", "is_active": True}]
        }
    }


class WhatsAppSaved(BaseModel):
    """Сохранённые значения привязки для ответа attach и list (id, tenant_id, phone_number, active, chatflow_instance_id, chatflow_token)."""
    id: int
    tenant_id: int
    phone_number: str
    active: bool
    chatflow_instance_id: Optional[str] = None
    chatflow_token: Optional[str] = None  # полное значение, чтобы фронт видел что сохранилось


# ========== CRM v3: Auto Assign Rules ==========

class AutoAssignRuleCreate(BaseModel):
    """POST /api/admin/tenants/{tenant_id}/auto-assign-rules."""
    name: str
    is_active: bool = True
    priority: int = 0
    match_city: Optional[str] = None
    match_language: Optional[str] = None
    match_object_type: Optional[str] = None
    match_contains: Optional[str] = None
    time_from: Optional[int] = Field(None, ge=0, le=23)
    time_to: Optional[int] = Field(None, ge=0, le=23)
    days_of_week: Optional[str] = None  # "1,2,3,4,5"
    strategy: str = "round_robin"  # round_robin | least_loaded | fixed_user
    fixed_user_id: Optional[int] = None


class AutoAssignRuleUpdate(BaseModel):
    """PATCH /api/admin/auto-assign-rules/{rule_id}."""
    name: Optional[str] = None
    is_active: Optional[bool] = None
    priority: Optional[int] = None
    match_city: Optional[str] = None
    match_language: Optional[str] = None
    match_object_type: Optional[str] = None
    match_contains: Optional[str] = None
    time_from: Optional[int] = Field(None, ge=0, le=23)
    time_to: Optional[int] = Field(None, ge=0, le=23)
    days_of_week: Optional[str] = None
    strategy: Optional[str] = None
    fixed_user_id: Optional[int] = None


class AutoAssignRuleResponse(BaseModel):
    """Правило автоназначения для ответа API."""
    id: int
    tenant_id: int
    name: str
    is_active: bool
    priority: int
    match_city: Optional[str] = None
    match_language: Optional[str] = None
    match_object_type: Optional[str] = None
    match_contains: Optional[str] = None
    time_from: Optional[int] = None
    time_to: Optional[int] = None
    days_of_week: Optional[str] = None
    strategy: str
    fixed_user_id: Optional[int] = None
    rr_state: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
