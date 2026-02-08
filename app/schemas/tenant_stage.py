"""
Pydantic schemas for TenantStage (owner-managed pipeline stages)
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class TenantStageBase(BaseModel):
    """Base schema for tenant stage"""
    stage_key: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z_]+$', description="Stage identifier (unique per tenant, e.g. 'unsorted')")
    title_ru: str = Field(..., min_length=1, max_length=100, description="Russian display name")
    title_kz: str = Field(..., min_length=1, max_length=100, description="Kazakh display name")
    order_index: int = Field(default=0, ge=0, description="Display order in Kanban (lower = left)")
    color: str = Field('#94a3b8', pattern=r'^#[0-9a-fA-F]{6}$', description="Hex color code (#FF5733)")


class TenantStageCreate(BaseModel):
    """Schema for creating a new stage"""
    stage_key: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z_]+$')
    title_ru: str = Field(..., min_length=1, max_length=100)
    title_kz: str = Field(..., min_length=1, max_length=100)
    order_index: int = Field(default=0, ge=0)
    color: str = Field('#94a3b8', pattern=r'^#[0-9a-fA-F]{6}$')


class TenantStageUpdate(BaseModel):
    """Schema for updating an existing stage"""
    title_ru: Optional[str] = Field(None, min_length=1, max_length=100)
    title_kz: Optional[str] = Field(None, min_length=1, max_length=100)
    order_index: Optional[int] = Field(None, ge=0)
    color: Optional[str] = Field(None, pattern=r'^#[0-9a-fA-F]{6}$')
    is_active: Optional[bool] = None


class TenantStageResponse(BaseModel):
    """Response schema for tenant stage"""
    id: int
    tenant_id: int
    stage_key: str
    title_ru: str
    title_kz: str
    color: str
    order_index: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class TenantStageReorderItem(BaseModel):
    """Single item in reorder request"""
    stage_id: int = Field(..., gt=0)
    order_index: int = Field(..., ge=0)


class TenantStageReorderBody(BaseModel):
    """Body for bulk reorder endpoint"""
    stages: list[TenantStageReorderItem] = Field(..., min_length=1, description="List of stage_id + order_index pairs")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "stages": [
                        {"stage_id": 1, "order_index": 0},
                        {"stage_id": 2, "order_index": 1},
                        {"stage_id": 3, "order_index": 2}
                    ]
                }
            ]
        }
    }


class TenantStagesResponse(BaseModel):
    """Response for GET /api/tenants/{id}/stages"""
    ok: bool = True
    stages: list[TenantStageResponse]
    total: int = Field(..., description="Total number of stages (including inactive if requested)")


class LeadStageUpdateBody(BaseModel):
    """Body for PATCH /api/leads/{id}/stage endpoint"""
    stage_key: str = Field(..., min_length=1, max_length=64, description="Target stage key")
    reason: Optional[str] = Field(None, max_length=512, description="Reason for manual stage change")
    
    model_config = {
        "json_schema_extra": {
            "examples": [
                {"stage_key": "wants_call", "reason": "Client requested callback"},
                {"stage_key": "lost", "reason": "No response after 3 followups"}
            ]
        }
    }
