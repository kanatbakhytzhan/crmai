"""
Lead categories API endpoints.
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.database import crud
from app.database.models import User
from app.schemas.lead import (
    LeadCategoryCreate,
    LeadCategoryResponse,
    LeadCategoriesResponse,
    LeadCategoryUpdateBody,
)
from app.api.error_handler import get_request_id, ValidationError
from app.core.config import get_settings

router = APIRouter()


@router.get("/lead-categories", summary="Список категорий лидов", response_model=LeadCategoriesResponse)
async def get_lead_categories_endpoint(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить все категории для текущего tenant.
    
    Returns:
    - ok: true
    - categories: список категорий с полями id, key, label, color, order_index
    - request_id: UUID запроса
    """
    # Определить tenant_id для пользователя
    tenant = await crud.get_tenant_for_me(db, current_user.id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found for current user"
        )
    
    categories = await crud.get_lead_categories(db, tenant_id=tenant.id, active_only=True)
    
    request_id = get_request_id(request)
    return LeadCategoriesResponse(
        ok=True,
        categories=[LeadCategoryResponse.model_validate(c) for c in categories],
        request_id=request_id
    )


@router.post("/lead-categories", summary="Создать/обновить категорию")
async def create_lead_category_endpoint(
    request: Request,
    body: LeadCategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Создать или обновить категорию лида для tenant.
    
    Request body:
    - key: ключ категории (hot, warm, cold, etc.)
    - label: человекочитаемое название
    - color: цвет в hex (#FF5733)
    - order_index: порядок сортировки
    
    Returns:
    - ok: true
    - category: созданная/обновленная категория
    - request_id: UUID запроса
    """
    # Определить tenant_id
    tenant = await crud.get_tenant_for_me(db, current_user.id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found for current user"
        )
    
    # Проверить роль (только owner/rop могут управлять категориями)
    role = await crud.get_tenant_user_role(db, tenant.id, current_user.id)
    if role not in ("owner", "rop"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owner or rop can manage categories"
        )
    
    # Создать/обновить категорию
    category = await crud.create_or_update_lead_category(
        db, tenant_id=tenant.id,
        key=body.key,
        label=body.label,
        color=body.color,
        order_index=body.order_index
    )
    
    request_id = get_request_id(request)
    return {
        "ok": True,
        "category": LeadCategoryResponse.model_validate(category).model_dump(),
        "request_id": request_id
    }


@router.patch("/leads/{lead_id}/category", summary="Изменить категорию лида")
async def update_lead_category_endpoint(
    lead_id: int,
    body: LeadCategoryUpdateBody,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновить категорию лида.
    
    Request body:
    - category_key: ключ новой категории
    
    Returns:
    - ok: true
    - lead: обновленный лид с новой категорией
    - request_id: UUID запроса
    """
    from app.schemas.lead import LeadResponse
    
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    
    # Обновить категорию лида
    lead = await crud.update_lead_category_key(
        db, lead_id=lead_id,
        category_key=body.category_key,
        current_user_id=current_user.id,
        multitenant_include_tenant_leads=multitenant
    )
    
    if not lead:
        # Проверить, лид не найден или категория не существует
        existing_lead = await crud.get_lead_by_id(
            db, lead_id=lead_id, owner_id=current_user.id,
            multitenant_include_tenant_leads=multitenant
        )
        if not existing_lead:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lead with ID {lead_id} not found"
            )
        else:
            raise ValidationError(
                message=f"Category '{body.category_key}' not found for this tenant",
                details={"category_key": body.category_key}
            )
    
    request_id = get_request_id(request)
    return {
        "ok": True,
        "lead": LeadResponse.model_validate(lead).model_dump(),
        "request_id": request_id
    }
