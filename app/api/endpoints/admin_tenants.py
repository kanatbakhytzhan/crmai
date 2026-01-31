"""
API эндпоинты админки: tenants и whatsapp_accounts (multi-tenant).
Доступ только для админа (как /api/admin/users).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.database import crud
from app.database.models import User
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
)

router = APIRouter()


@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Создать tenant (name, slug, optional default_owner_user_id)."""
    existing = await crud.get_tenant_by_slug(db, body.slug)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant with this slug already exists",
        )
    tenant = await crud.create_tenant(
        db,
        name=body.name,
        slug=body.slug,
        default_owner_user_id=body.default_owner_user_id,
    )
    return TenantResponse.model_validate(tenant)


@router.patch("/tenants/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: int,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Обновить tenant: name, slug, is_active, default_owner_user_id."""
    tenant = await crud.update_tenant(
        db,
        tenant_id,
        name=body.name,
        slug=body.slug,
        is_active=body.is_active,
        default_owner_user_id=body.default_owner_user_id,
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)


@router.get("/tenants", response_model=dict)
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Список tenants."""
    tenants = await crud.list_tenants(db)
    return {"tenants": [TenantResponse.model_validate(t) for t in tenants], "total": len(tenants)}


@router.post("/tenants/{tenant_id}/whatsapp", response_model=WhatsAppAccountResponse, status_code=status.HTTP_201_CREATED)
async def attach_whatsapp(
    tenant_id: int,
    body: WhatsAppAccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Привязать WhatsApp номер к tenant."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    acc = await crud.create_whatsapp_account(
        db,
        tenant_id=tenant_id,
        phone_number=body.phone_number,
        phone_number_id=body.phone_number_id,
        verify_token=body.verify_token,
        waba_id=body.waba_id,
    )
    return WhatsAppAccountResponse.model_validate(acc)


@router.get("/tenants/{tenant_id}/whatsapp", response_model=dict)
async def list_whatsapp(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Список WhatsApp номеров tenant."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
    return {"accounts": [WhatsAppAccountResponse.model_validate(a) for a in accounts], "total": len(accounts)}


@router.delete("/tenants/{tenant_id}/whatsapps/{whatsapp_id}")
async def delete_tenant_whatsapp(
    tenant_id: int,
    whatsapp_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Удалить WhatsApp номер у tenant (только если tenant_id совпадает)."""
    deleted = await crud.delete_whatsapp_account(db, tenant_id=tenant_id, whatsapp_id=whatsapp_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WhatsApp account not found or tenant mismatch")
    return {"ok": True}
