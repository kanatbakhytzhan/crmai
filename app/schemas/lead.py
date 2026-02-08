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


class CategoryEnum(str, Enum):
    """AI CRM Manager категории лидов"""
    NO_REPLY = "no_reply"
    WANTS_CALL = "wants_call"
    PARTIAL_DATA = "partial_data"
    FULL_DATA = "full_data"
    MEASUREMENT_ASSIGNED = "measurement_assigned"
    MEASUREMENT_DONE = "measurement_done"
    REJECTED = "rejected"
    WON = "won"


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
    updated_at: Optional[datetime] = None  # для сортировки
    last_comment: Optional[str] = None  # preview последнего комментария (до 100 символов)
    last_message_preview: Optional[str] = None  # для мобильных карточек
    lead_number: Optional[int] = None  # CRM v2: порядковый номер лида
    tenant_id: Optional[int] = None
    assigned_user_id: Optional[int] = None
    assigned_to_user_id: Optional[int] = None  # alias для API (то же что assigned_user_id)
    assigned_at: Optional[datetime] = None
    assigned_user_email: Optional[str] = None
    assigned_user_name: Optional[str] = None  # company_name
    next_call_at: Optional[datetime] = None
    last_contact_at: Optional[datetime] = None
    pipeline_id: Optional[int] = None
    stage_id: Optional[int] = None
    moved_to_stage_at: Optional[datetime] = None
    first_response_at: Optional[datetime] = None
    first_assigned_at: Optional[datetime] = None
    source: Optional[str] = None
    external_source: Optional[str] = None
    external_id: Optional[str] = None
    
    # CRM v3: категории лидов
    category_key: Optional[str] = None
    category_label: Optional[str] = None
    category_color: Optional[str] = None
    category_order: Optional[int] = None
    
    # AI CRM Manager fields (Phase A-F)
    category: Optional[str] = None  # no_reply, wants_call, partial_data, full_data
    lead_score: Optional[str] = None  # hot, warm, cold
    handoff_mode: Optional[str] = None  # ai | human
    extracted_fields: Optional[dict] = None  # JSON data from conversation
    last_inbound_at: Optional[datetime] = None  # last message FROM client
    last_outbound_at: Optional[datetime] = None  # last message TO client

    model_config = {"from_attributes": True}

    @field_validator("status", mode="before")
    @classmethod
    def status_to_str(cls, v):
        """Enum из БД приводим к строке для API/CRM."""
        if hasattr(v, "value"):
            return v.value
        return str(v) if v is not None else "new"


class LeadCommentCreate(BaseModel):
    """Создание комментария к лиду. POST /api/leads/{lead_id}/comments."""
    text: str = Field(..., min_length=1, description="Текст комментария")

    model_config = {
        "json_schema_extra": {
            "examples": [{"text": "Клиент перезвонил, договорились на замер в среду."}]
        }
    }


class AIMuteUpdate(BaseModel):
    """POST /api/leads/{lead_id}/ai-mute — включить/выключить AI в чате лида."""
    muted: bool = Field(..., description="true = отключить AI в этом чате, false = включить")

    model_config = {
        "json_schema_extra": {
            "examples": [{"muted": True}, {"muted": False}]
        }
    }


class AIChatMuteBody(BaseModel):
    """POST /api/ai/mute — mute по chat_key (remoteJid или phone:...)."""
    chat_key: str = Field(..., min_length=1, description="Уникальный ключ чата: remoteJid или phone:...")
    muted: bool = Field(..., description="true = отключить AI, false = включить")

    model_config = {
        "json_schema_extra": {
            "examples": [{"chat_key": "77001234567@s.whatsapp.net", "muted": True}]
        }
    }


class LeadAssignBody(BaseModel):
    """PATCH /api/leads/{id}/assign. Назначить лид на менеджера (owner/rop)."""
    assigned_to_user_id: Optional[int] = None
    assigned_user_id: Optional[int] = None  # legacy alias
    status: Optional[str] = None

    def get_assigned_user_id(self) -> Optional[int]:
        return self.assigned_to_user_id if self.assigned_to_user_id is not None else self.assigned_user_id

    model_config = {
        "json_schema_extra": {
            "examples": [{"assigned_to_user_id": 5}, {"assigned_to_user_id": None, "status": "in_progress"}]
        }
    }


class LeadBulkAssignBody(BaseModel):
    """POST /api/leads/assign/bulk. Массовое назначение лидов на одного менеджера (owner/rop)."""
    lead_ids: list[int]
    assigned_to_user_id: Optional[int] = None
    assigned_user_id: Optional[int] = None  # legacy alias
    set_status: Optional[str] = None

    def get_assigned_user_id(self) -> Optional[int]:
        return self.assigned_to_user_id if self.assigned_to_user_id is not None else self.assigned_user_id

    model_config = {
        "json_schema_extra": {
            "examples": [{"lead_ids": [1, 2, 3], "assigned_to_user_id": 5, "set_status": "in_progress"}]
        }
    }


class LeadPatchBody(BaseModel):
    """PATCH /api/leads/{id} — status, next_call_at, last_contact_at, assigned_user_id, category, handoff_mode (owner/rop)."""
    status: Optional[str] = None
    next_call_at: Optional[datetime] = None
    last_contact_at: Optional[datetime] = None
    assigned_user_id: Optional[int] = None
    # AI CRM Manager fields
    category: Optional[CategoryEnum] = None
    handoff_mode: Optional[Literal['ai', 'human']] = None


class LeadStageBody(BaseModel):
    """PATCH /api/leads/{id}/stage — перемещение по воронке."""
    stage_id: int


class LeadSelectionFilters(BaseModel):
    """Фильтры для POST /api/leads/selection."""
    status: Optional[list[str]] = None
    stage_id: Optional[list[int]] = None
    assigned: Optional[str] = None  # any | none | mine
    city: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    search: Optional[str] = None


class LeadSelectionBody(BaseModel):
    """POST /api/leads/selection."""
    filters: Optional[LeadSelectionFilters] = None
    sort: str = "created_at"
    direction: str = "desc"
    limit: int = 500


class AssignPlanItem(BaseModel):
    """Один элемент плана: by_ranges."""
    manager_user_id: int
    from_index: int
    to_index: int


class LeadAssignPlanBody(BaseModel):
    """POST /api/leads/assign/plan."""
    lead_ids: list[int]
    mode: str = "by_ranges"  # by_ranges | by_counts | round_robin
    plans: list[AssignPlanItem] = []
    set_status: Optional[str] = None
    dry_run: bool = False


class LeadCommentResponse(BaseModel):
    """Комментарий к лиду"""
    id: int
    lead_id: int
    user_id: int
    text: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ========== CRM v3: Import ==========

class ImportLeadsResponse(BaseModel):
    """Ответ POST /api/admin/import/leads."""
    ok: bool
    mode: str  # dry_run | commit
    total_rows: int = 0
    created: int = 0
    skipped: int = 0
    errors: list[str] = []
    preview: list[dict] = []  # первые 20 для dry_run


# ========== CRM v3: Assign by range ==========

class AssignByRangeBody(BaseModel):
    """POST /api/admin/leads/assign/by-range."""
    tenant_id: int
    from_index: int = Field(..., ge=1, description="Начальный индекс (1-based)")
    to_index: int = Field(..., ge=1, description="Конечный индекс (1-based)")
    strategy: str = "round_robin"  # round_robin | fixed_user | custom_map
    fixed_user_id: Optional[int] = None
    custom_map: Optional[list[dict]] = None  # [{"user_id": 10, "count": 5}, ...]
    filters: Optional[dict] = None  # {"status": "new", "only_unassigned": true}

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"tenant_id": 2, "from_index": 5, "to_index": 12, "strategy": "round_robin", "filters": {"status": "new", "only_unassigned": True}},
            ]
        }
    }


class AssignByRangeResponse(BaseModel):
    ok: bool
    total_selected: int = 0
    assigned: int = 0
    skipped: int = 0
    details: list[dict] = []


# ========== API Response Schemas ==========

class LeadListResponse(BaseModel):
    """Response for GET /api/leads with pagination."""
    ok: bool = True
    leads: list[LeadResponse]
    total: int
    page: int = 1
    limit: int = 50
    request_id: str


class LeadStatsResponse(BaseModel):
    """Response for GET /api/leads/stats."""
    ok: bool = True
    stats: dict[str, int]  # {"new": 15, "in_progress": 8, "done": 42, "cancelled": 3, "total": 68}
    last_updated: datetime
    request_id: str


# ========== Lead Category Schemas ==========

class LeadCategoryBase(BaseModel):
    """Base schema for lead category."""
    key: str
    label: str
    color: Optional[str] = None
    order_index: int = 0


class LeadCategoryCreate(LeadCategoryBase):
    """Schema for creating a lead category."""
    pass


class LeadCategoryUpdate(BaseModel):
    """Schema for updating a lead category."""
    label: Optional[str] = None
    color: Optional[str] = None
    order_index: Optional[int] = None
    is_active: Optional[bool] = None


class LeadCategoryResponse(LeadCategoryBase):
    """Response schema for lead category."""
    id: int
    tenant_id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class LeadCategoryUpdateBody(BaseModel):
    """Body for PATCH /api/leads/{id}/category."""
    category_key: str


class LeadCategoriesResponse(BaseModel):
    """Response for GET /api/lead-categories."""
    ok: bool = True
    categories: list[LeadCategoryResponse]
    request_id: str
