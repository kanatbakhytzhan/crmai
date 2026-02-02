"""
API эндпоинты админки: tenants и whatsapp_accounts (multi-tenant).
Доступ только для админа (как /api/admin/users).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin
from app.database import crud
from app.database.models import User
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    AISettingsResponse,
    AISettingsUpdate,
    TenantUserAdd,
    TenantUserResponse,
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
    WhatsAppAccountUpsert,
    WhatsAppSaved,
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
    """Обновить tenant: name, slug, is_active, default_owner_user_id, ai_enabled, ai_prompt, webhook_key."""
    tenant = await crud.update_tenant(
        db,
        tenant_id,
        name=body.name,
        slug=body.slug,
        is_active=body.is_active,
        default_owner_user_id=body.default_owner_user_id,
        ai_enabled=body.ai_enabled,
        ai_prompt=body.ai_prompt,
        webhook_key=body.webhook_key,
    )
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantResponse.model_validate(tenant)


@router.get("/tenants/{tenant_id}", response_model=dict)
async def get_tenant(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Один tenant + текущая привязка WhatsApp (whatsapp_connection) для формы редактирования."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
    whatsapp_connection = WhatsAppAccountResponse.model_validate(accounts[0]) if accounts else None
    return {"tenant": TenantResponse.model_validate(tenant), "whatsapp_connection": whatsapp_connection}


@router.get("/tenants", response_model=dict)
async def list_tenants(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Список tenants."""
    tenants = await crud.list_tenants(db)
    return {"tenants": [TenantResponse.model_validate(t) for t in tenants], "total": len(tenants)}


@router.get("/tenants/{tenant_id}/users", response_model=dict)
async def list_tenant_users(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Список пользователей tenant (tenant_users + данные User).
    Привязка пользователей к tenant для доступа к лидам и CRM.
    """
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    rows = await crud.list_tenant_users_with_user(db, tenant_id)
    items = [
        TenantUserResponse(
            id=tu.id,
            user_id=user.id,
            email=user.email,
            company_name=user.company_name,
            role=tu.role or "member",
            created_at=tu.created_at,
        )
        for tu, user in rows
    ]
    return {"users": items, "total": len(items)}


@router.post("/tenants/{tenant_id}/users", response_model=TenantUserResponse, status_code=status.HTTP_201_CREATED)
async def add_tenant_user(
    tenant_id: int,
    body: TenantUserAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Добавить пользователя к tenant по email и role.
    Body: { "email": "user@mail.com", "role": "manager" | "admin" | "member" }.
    Если пользователь уже в tenant — возвращаем существующую запись (не 409).
    """
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    user = await crud.get_user_by_email(db, email=body.email)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_not_found")
    role = (body.role or "member").strip().lower() or "member"
    if role not in ("manager", "admin", "member"):
        role = "member"
    tu = await crud.create_tenant_user(db, tenant_id=tenant_id, user_id=user.id, role=role)
    return TenantUserResponse(
        id=tu.id,
        user_id=user.id,
        email=user.email,
        company_name=user.company_name,
        role=tu.role or "member",
        created_at=tu.created_at,
    )


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def remove_tenant_user(
    tenant_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Удалить пользователя из tenant."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    deleted = await crud.delete_tenant_user(db, tenant_id=tenant_id, user_id=user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not in tenant or not found")
    return {"ok": True}


@router.get("/tenants/{tenant_id}/ai-settings", response_model=AISettingsResponse)
async def get_ai_settings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Настройки AI для tenant: ai_enabled, ai_prompt."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return AISettingsResponse(
        ai_enabled=getattr(tenant, "ai_enabled", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
    )


@router.patch("/tenants/{tenant_id}/ai-settings", response_model=AISettingsResponse)
async def update_ai_settings(
    tenant_id: int,
    body: AISettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Обновить настройки AI: ai_enabled, ai_prompt (без изменения остальных полей tenant)."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    await crud.update_tenant(
        db,
        tenant_id,
        ai_enabled=body.ai_enabled,
        ai_prompt=body.ai_prompt,
    )
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    return AISettingsResponse(
        ai_enabled=getattr(tenant, "ai_enabled", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
    )


@router.put("/tenants/{tenant_id}/whatsapp", response_model=WhatsAppAccountResponse)
async def upsert_whatsapp(
    tenant_id: int,
    body: WhatsAppAccountUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Сохранить/обновить привязку WhatsApp/ChatFlow для tenant (одна запись на tenant).
    Если запись уже есть — обновить; если нет — создать.
    При active=true обязательны chatflow_token и chatflow_instance_id (иначе бот не отвечает).
    """
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if body.is_active:
        token_ok = (body.chatflow_token or "").strip()
        instance_ok = (body.chatflow_instance_id or "").strip()
        if not token_ok or not instance_ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="When active=true, chatflow_token and chatflow_instance_id are required",
            )
    phone_number = (body.phone_number or "").strip() or "—"
    instance_id = (body.chatflow_instance_id or "").strip() or None
    token = (body.chatflow_token or "").strip() or None
    print("[ADMIN] whatsapp upsert tenant_id=%s active=%s phone_number=%s token_len=%s instance_len=%s", tenant_id, body.is_active, phone_number, len(body.chatflow_token or ""), len(body.chatflow_instance_id or ""))
    acc = await crud.upsert_whatsapp_for_tenant(
        db,
        tenant_id=tenant_id,
        phone_number=phone_number,
        chatflow_token=token,
        chatflow_instance_id=instance_id,
        is_active=body.is_active,
    )
    print("[ADMIN] whatsapp upsert saved id=%s", acc.id)
    return WhatsAppAccountResponse.model_validate(acc)


def _whatsapp_to_saved(acc) -> WhatsAppSaved:
    """Собрать объект сохранённой привязки для ответа (id, tenant_id, phone_number, active, chatflow_instance_id, chatflow_token)."""
    return WhatsAppSaved(
        id=acc.id,
        tenant_id=acc.tenant_id,
        phone_number=acc.phone_number or "—",
        active=getattr(acc, "is_active", True),
        chatflow_instance_id=getattr(acc, "chatflow_instance_id", None) or None,
        chatflow_token=(getattr(acc, "chatflow_token", None) or "").strip() or None,
    )


@router.post("/tenants/{tenant_id}/whatsapp", status_code=status.HTTP_201_CREATED)
async def attach_whatsapp(
    tenant_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Привязать/обновить WhatsApp (UPSERT): одна запись на tenant.
    Принимает token или chatflow_token, instance_id или chatflow_instance_id, active или is_active.
    При active=true обязательны chatflow_token и chatflow_instance_id (422 при отсутствии).
    При active=false можно без token/instance_id (существующие не затираются).
    Ответ: { ok: true, whatsapp: { id, tenant_id, phone_number, active, chatflow_instance_id, chatflow_token } }.
    """
    try:
        body_raw = await request.json()
    except Exception:
        body_raw = {}
    body_raw_keys = list(body_raw.keys()) if isinstance(body_raw, dict) else []
    try:
        body = WhatsAppAccountCreate.model_validate(body_raw)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    if body.is_active:
        token_ok = (body.chatflow_token or "").strip()
        instance_ok = (body.chatflow_instance_id or "").strip()
        if not token_ok or not instance_ok:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="When active=true, chatflow_token and chatflow_instance_id are required (non-empty)",
            )
    token = (body.chatflow_token or "").strip() or None
    instance_id = (body.chatflow_instance_id or "").strip() or None
    phone_number = (body.phone_number or "").strip() or "—"
    token_len = len(body.chatflow_token or "")
    instance_len = len(body.chatflow_instance_id or "")
    print(
        "[ADMIN] whatsapp attach tenant_id=%s active=%s phone_number=%s token_len=%s instance_len=%s json_keys=%s",
        tenant_id, body.is_active, phone_number, token_len, instance_len, body_raw_keys,
    )
    acc = await crud.upsert_whatsapp_for_tenant(
        db,
        tenant_id=tenant_id,
        phone_number=phone_number,
        phone_number_id=body.phone_number_id,
        chatflow_token=token,
        chatflow_instance_id=instance_id,
        is_active=body.is_active,
    )
    print("[ADMIN] whatsapp attach saved id=%s", acc.id)
    return {"ok": True, "whatsapp": _whatsapp_to_saved(acc)}


@router.get("/tenants/{tenant_id}/whatsapp", response_model=dict)
async def list_whatsapp(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Список привязок WhatsApp tenant с полями: id, tenant_id, phone_number, active, chatflow_instance_id, chatflow_token."""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
    items = [_whatsapp_to_saved(a) for a in accounts]
    return {"ok": True, "whatsapp": items, "total": len(items)}


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
