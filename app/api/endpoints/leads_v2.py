"""
CRM v2 API (feature-flag CRM_V2_ENABLED).
GET /api/v2/leads/table — лиды в формате для таблицы (только admin).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.api.deps import get_db, get_current_admin
from app.core.config import get_settings
from app.database import crud
from app.database.models import User

router = APIRouter()


class LeadTableRow(BaseModel):
    """Строка для таблицы лидов (CRM v2)."""
    lead_number: Optional[int] = None
    name: str
    phone: str
    city: Optional[str] = None
    object_type: Optional[str] = None
    area: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class LeadsTableResponse(BaseModel):
    """Единый контракт списка лидов: основной ключ — leads (как в GET /api/leads). rows — дубликат на один релиз для обратной совместимости."""
    ok: bool = True
    leads: list[LeadTableRow]  # основной ключ (как в GET /api/leads)
    rows: list[LeadTableRow]   # deprecated: дубликат leads, будет удалён
    total: int


@router.get(
    "/leads/table",
    response_model=LeadsTableResponse,
    summary="Список лидов для таблицы (v2)",
    response_description="**Основной ключ — `leads`** (как в GET /api/leads). Поле `rows` — дубликат для обратной совместимости, будет удалён.",
)
async def get_leads_table(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Лиды в формате для таблицы: lead_number, name, phone, city, object_type, area, status, created_at.
    Контракт совпадает с GET /api/leads: **{ leads, total }**. Дополнительно возвращаются `ok` и `rows` (rows = leads, на один релиз).
    Только для ROP/Admin. Доступно только при CRM_V2_ENABLED=true.
    """
    settings = get_settings()
    if (getattr(settings, "crm_v2_enabled", "false") or "false").upper() != "TRUE":
        raise HTTPException(status_code=404, detail="CRM v2 is disabled (CRM_V2_ENABLED)")
    multitenant = (getattr(settings, "multitenant_enabled", "false") or "false").upper() == "TRUE"
    leads = await crud.get_user_leads(
        db,
        owner_id=current_user.id,
        limit=1000,
        multitenant_include_tenant_leads=multitenant,
    )
    items = []
    for l in leads:
        status_str = l.status.value if hasattr(l.status, "value") else str(l.status or "new")
        items.append(
            LeadTableRow(
                lead_number=getattr(l, "lead_number", None),
                name=l.name or "",
                phone=l.phone or "",
                city=l.city,
                object_type=l.object_type,
                area=l.area,
                status=status_str,
                created_at=l.created_at,
            )
        )
    return LeadsTableResponse(ok=True, leads=items, rows=items, total=len(items))
