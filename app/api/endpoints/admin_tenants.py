"""
API эндпоинты админки: tenants и whatsapp_accounts (multi-tenant).
Доступ только для админа (как /api/admin/users).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_admin, get_current_user
from app.database import crud
from app.database.models import User
from app.schemas.tenant import (
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    AISettingsResponse,
    AISettingsUpdate,
    TenantUserAdd,
    TenantUserPatch,
    TenantUserResponse,
    WhatsAppAccountCreate,
    WhatsAppAccountResponse,
    WhatsAppAccountUpsert,
    WhatsAppSaved,
)

router = APIRouter()


def _tenant_response(tenant, base_url: str) -> dict:
    """TenantResponse с вычисляемым webhook_url. Handles missing columns gracefully."""
    try:
        from app.schemas.tenant import TenantResponse
        data = TenantResponse.model_validate(tenant).model_dump()
    except Exception:
        # Fallback if model_validate fails (e.g., missing columns in DB)
        data = {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "is_active": tenant.is_active,
            "default_owner_user_id": getattr(tenant, "default_owner_user_id", None),
            "ai_enabled": getattr(tenant, "ai_enabled", True),
            "ai_prompt": getattr(tenant, "ai_prompt", None),
            "webhook_key": getattr(tenant, "webhook_key", None),
            "webhook_url": None,
            "whatsapp_source": getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
            "ai_enabled_global": getattr(tenant, "ai_enabled_global", True),
            "ai_after_lead_submitted_behavior": getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close"),
            "created_at": tenant.created_at,
        }
    base = (base_url or "").rstrip("/")
    if getattr(tenant, "webhook_key", None) and base:
        data["webhook_url"] = f"{base}/api/chatflow/webhook?key={tenant.webhook_key}"
    else:
        data["webhook_url"] = None
    return data


@router.post("/tenants", status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: Request,
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Создать tenant (name, slug, optional default_owner_user_id). webhook_key генерируется автоматически."""
    from app.core.config import get_settings
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
    base_url = get_settings().public_base_url or str(request.base_url).rstrip("/")
    return _tenant_response(tenant, base_url)


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    request: Request,
    tenant_id: int,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Обновить tenant: name, slug, is_active, default_owner_user_id, ai_enabled, ai_prompt, webhook_key."""
    from app.core.config import get_settings
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
    base_url = get_settings().public_base_url or str(request.base_url).rstrip("/")
    return _tenant_response(tenant, base_url)


@router.get("/tenants/{tenant_id}", response_model=dict)
async def get_tenant(
    request: Request,
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Один tenant + текущая привязка WhatsApp (whatsapp_connection). webhook_url в tenant."""
    from app.core.config import get_settings
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
    whatsapp_connection = WhatsAppAccountResponse.model_validate(accounts[0]) if accounts else None
    base_url = get_settings().public_base_url or str(request.base_url).rstrip("/")
    return {"tenant": _tenant_response(tenant, base_url), "whatsapp_connection": whatsapp_connection}


@router.get("/tenants", response_model=dict)
async def list_tenants(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Список tenants. В каждом tenant есть webhook_key и webhook_url."""
    import traceback
    try:
        from app.core.config import get_settings
        tenants = await crud.list_tenants(db)
        base_url = get_settings().public_base_url or str(request.base_url).rstrip("/")
        return {"tenants": [_tenant_response(t, base_url) for t in tenants], "total": len(tenants)}
    except Exception as e:
        print(f"[ERROR] list_tenants failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal error: {type(e).__name__}")


async def _require_tenant_admin_or_owner_rop(db: AsyncSession, tenant_id: int, current_user: User) -> str | None:
    """Проверка доступа: admin или owner/rop в tenant. Возвращает роль или None (403)."""
    if getattr(current_user, "is_admin", False):
        return "admin"
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    if role in ("owner", "rop"):
        return role
    return None


@router.get("/tenants/{tenant_id}/users", response_model=dict)
async def list_tenant_users(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Список пользователей tenant (tenant_users + User). CRM v2.5: parent_user_id, is_active.
    Доступ: admin или owner/rop в этом tenant.
    """
    if not await _require_tenant_admin_or_owner_rop(db, tenant_id, current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")
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
            parent_user_id=getattr(tu, "parent_user_id", None),
            is_active=getattr(tu, "is_active", True),
            created_at=tu.created_at,
        )
        for tu, user in rows
    ]
    return {"users": items, "total": len(items)}


@router.post("/tenants/{tenant_id}/users", status_code=status.HTTP_201_CREATED)
async def add_tenant_user(
    tenant_id: int,
    body: TenantUserAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Добавить пользователя к tenant. Body: email, role, parent_user_id?, is_active?.
    ROP может создавать только manager с parent_user_id = self. Если пользователя нет — создаём с temporary_password.
    """
    import secrets
    access = await _require_tenant_admin_or_owner_rop(db, tenant_id, current_user)
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")
    role = (body.role or "member").strip().lower() or "manager"
    if role not in ("owner", "rop", "manager", "admin", "member"):
        role = "manager"
    if access == "rop":
        if role != "manager":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ROP can only add managers")
        if body.parent_user_id is not None and body.parent_user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ROP must set parent_user_id to self")
        parent_user_id = current_user.id
    else:
        parent_user_id = body.parent_user_id
    is_active = body.is_active if body.is_active is not None else True
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    user = await crud.get_user_by_email(db, email=body.email.strip())
    temporary_password = None
    if not user:
        temporary_password = secrets.token_urlsafe(12)
        user = await crud.create_user(
            db, email=body.email.strip(), password=temporary_password, company_name=body.email.strip().split("@")[0] or "User"
        )
    tu = await crud.create_tenant_user(db, tenant_id=tenant_id, user_id=user.id, role=role, parent_user_id=parent_user_id, is_active=is_active)
    out = {
        "ok": True,
        "user": TenantUserResponse(
            id=tu.id,
            user_id=user.id,
            email=user.email,
            company_name=user.company_name,
            role=tu.role or role,
            parent_user_id=getattr(tu, "parent_user_id", None),
            is_active=getattr(tu, "is_active", True),
            created_at=tu.created_at,
        ),
    }
    if temporary_password:
        out["temporary_password"] = temporary_password
    return out


@router.patch("/tenants/users/{tenant_user_id}", response_model=dict)
async def patch_tenant_user(
    tenant_user_id: int,
    body: TenantUserPatch,
    tenant_id: int = Query(..., description="tenant_id для проверки доступа"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить tenant_user: role, parent_user_id, is_active. ROP — только managers, parent_user_id=self."""
    access = await _require_tenant_admin_or_owner_rop(db, tenant_id, current_user)
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")
    tu = await crud.get_tenant_user_by_id(db, tenant_user_id)
    if not tu or tu.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
    if access == "rop" and (tu.role or "").lower() != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ROP can only edit managers")
    if access == "rop" and body.parent_user_id is not None and body.parent_user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ROP must set parent_user_id to self")
    updated = await crud.update_tenant_user(
        db, tenant_user_id, tenant_id,
        role=body.role,
        parent_user_id=body.parent_user_id,
        is_active=body.is_active,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
    u = await crud.get_user_by_id(db, updated.user_id)
    return {
        "ok": True,
        "user": TenantUserResponse(
            id=updated.id,
            user_id=updated.user_id,
            email=u.email if u else "",
            company_name=u.company_name if u else None,
            role=updated.role or "member",
            parent_user_id=getattr(updated, "parent_user_id", None),
            is_active=getattr(updated, "is_active", True),
            created_at=updated.created_at,
        ),
    }


@router.delete("/tenants/users/{tenant_user_id}", response_model=dict)
async def soft_delete_tenant_user_by_id(
    tenant_user_id: int,
    tenant_id: int = Query(..., description="tenant_id для проверки доступа"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete: is_active=false. ROP — только для managers."""
    access = await _require_tenant_admin_or_owner_rop(db, tenant_id, current_user)
    if not access:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")
    tu = await crud.get_tenant_user_by_id(db, tenant_user_id)
    if not tu or tu.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
    if access == "rop" and (tu.role or "").lower() != "manager":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="ROP can only deactivate managers")
    ok = await crud.soft_delete_tenant_user(db, tenant_user_id, tenant_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant user not found")
    return {"ok": True}


@router.delete("/tenants/{tenant_id}/users/{user_id}")
async def remove_tenant_user(
    tenant_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """Удалить пользователя из tenant (hard delete). Только админ."""
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
