"""
CRM v2.5: in-app уведомления. GET /api/notifications, POST read, read-all.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.database import crud
from app.database.models import User

router = APIRouter(tags=["Notifications"])


class NotificationOut(BaseModel):
    id: int
    tenant_id: Optional[int]
    user_id: int
    type: str
    title: Optional[str]
    body: Optional[str]
    is_read: bool
    created_at: datetime
    lead_id: Optional[int]

    class Config:
        from_attributes = True


@router.get("/notifications", response_model=dict)
async def list_notifications(
    unread: bool = Query(True, description="только непрочитанные"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список уведомлений текущего пользователя."""
    items = await crud.notifications_for_user(db, current_user.id, unread_only=unread, limit=100)
    return {"notifications": [NotificationOut.model_validate(n) for n in items], "total": len(items)}


@router.post("/notifications/{notification_id}/read", response_model=dict)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметить уведомление прочитанным."""
    ok = await crud.notification_mark_read(db, notification_id, current_user.id)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"ok": True}


@router.post("/notifications/read-all", response_model=dict)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Отметить все уведомления пользователя прочитанными."""
    count = await crud.notification_mark_all_read(db, current_user.id)
    return {"ok": True, "marked": count}
