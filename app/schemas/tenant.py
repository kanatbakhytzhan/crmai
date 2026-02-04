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
    """
    Snapshot of ChatFlow binding for tenant settings response.
    
    For admin/owner: chatflow_token contains the FULL token.
    For other roles: chatflow_token is None, only chatflow_token_masked is returned.
    """
    binding_exists: bool = False
    is_active: bool = False
    accounts_count: int = 0
    phone_number: Optional[str] = None
    chatflow_instance_id: Optional[str] = None
    chatflow_token_masked: Optional[str] = None
    chatflow_token: Optional[str] = None  # Full token for admin/owner only


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
    clear_fields: Optional[list[str]] = Field(default_factory=list, description="Список полей для принудительной очистки (например: ['ai_prompt', 'amocrm_base_domain'])")


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

# Extended stage keys for AmoCRM mapping
# These cover common CRM stages including user's AmoCRM pipeline
STAGE_KEYS = [
    # Basic stages
    "UNREAD",           # Неразобранные / unsorted
    "UNSORTED",         # Неразобранные (alias)
    "NEW",              # Новые
    "IN_WORK",          # В работе
    
    # Call stages
    "CALL_1",           # 1-й звонок
    "CALL_2",           # 2-й звонок  
    "CALL_3",           # 3-й звонок
    
    # Special stages
    "REPAIR_NOT_READY", # Ремонт не готов
    "OTHER_CITY",       # Другой город
    "IGNORE",           # Игнор
    
    # Measurement stages
    "MEASUREMENT_ASSIGNED",     # Назначен замер
    "MEASUREMENT_DONE",         # Провел замер
    "AFTER_MEASUREMENT_REJECT", # Отказ после замера
    
    # System stages
    "WON",              # Успешно реализовано
    "LOST",             # Закрыто и не реализовано
    
    # Custom stages (for flexibility)
    "CUSTOM_1",
    "CUSTOM_2",
    "CUSTOM_3",
]


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


class AIChatMute(BaseModel):
    pass


class AuditLog(BaseModel):
    pass


class Notification(BaseModel):
    pass


# ========== Universal Admin Console: AmoCRM Pipelines ==========

class AmoPrimaryPipelineUpdate(BaseModel):
    """PUT /api/admin/tenants/{id}/amocrm/primary-pipeline"""
    pipeline_id: str = Field(..., description="ID основной воронки в AmoCRM")

class AmoPipelineMappingUpdate(BaseModel):
    """PUT /api/admin/tenants/{id}/amocrm/pipeline-mapping"""
    primary_pipeline_id: str = Field(..., description="ID основной воронки (пустая строка = сброс)")
    mapping: dict[str, str] | list[dict] = Field(..., description="Маппинг stage_key -> amo_stage_id. Support dict or list of {stage_key, stage_id}")

class AmoPipelineMappingResponse(BaseModel):
    """GET /api/admin/tenants/{id}/amocrm/pipeline-mapping"""
    primary_pipeline_id: Optional[str] = None
    mapping: dict[str, str] = {}
