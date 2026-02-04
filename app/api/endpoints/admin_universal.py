"""
Universal Admin Console API endpoints.
Tenant settings, AmoCRM connect, pipeline/field mappings, mute from lead, diagnostics.
"""
import traceback
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_current_admin_or_owner_or_rop
from app.database import crud
from app.database.models import User
from app.schemas.tenant import (
    TenantSettingsResponse,
    TenantSettingsUpdate,
    TenantSettingsBlock,
    ChatFlowBindingSnapshot,
    AmoCRMSnapshot,
    MappingsSnapshot,
    AmoCRMAuthUrlResponse,
    AmoCRMCallbackBody,
    AmoCRMStatusResponse,
    PipelineMappingResponse,
    PipelineMappingBulkUpdate,
    FieldMappingResponse,
    FieldMappingBulkUpdate,
    LeadMuteBody,
    LeadMuteResponse,
)
from app.services import amocrm_service

router = APIRouter()

# Публичный callback для AmoCRM OAuth (без auth, т.к. это redirect от amoCRM)
integrations_router = APIRouter()


def _safe_json_error(detail: str, status_code: int = 500) -> JSONResponse:
    """Return a safe JSON error response."""
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "detail": str(detail)[:500]}
    )


def _normalize_amocrm_domain(raw_input: str) -> str:
    """
    Normalize AmoCRM domain from various input formats to just the host.
    
    Accepts:
        - "company.amocrm.ru"
        - "https://company.amocrm.ru"
        - "https://company.amocrm.ru/leads/"
        - "http://company.amocrm.ru/leads/pipeline/123"
        - "company.kommo.com/anything"
    
    Returns:
        - "company.amocrm.ru" (just the host, lowercase)
    """
    from urllib.parse import urlparse
    
    domain = (raw_input or "").strip().lower()
    if not domain:
        return ""
    
    # If it doesn't have a scheme, add one for parsing
    if not domain.startswith(("http://", "https://")):
        domain = "https://" + domain
    
    try:
        parsed = urlparse(domain)
        host = parsed.netloc or parsed.path.split("/")[0]
        # Remove port if present
        host = host.split(":")[0]
        return host.lower().strip()
    except Exception:
        # Fallback: manual parsing
        domain = raw_input.strip().lower()
        if domain.startswith("https://"):
            domain = domain[8:]
        elif domain.startswith("http://"):
            domain = domain[7:]
        # Remove path
        domain = domain.split("/")[0]
        # Remove port
        domain = domain.split(":")[0]
        return domain.strip()


async def _require_tenant_access(db: AsyncSession, tenant_id: int, current_user: User) -> str:
    """
    Проверка доступа к настройкам tenant. Возвращает роль.
    
    Access rules:
    - admin (is_admin=True) -> allow for ANY tenant
    - owner (default_owner_user_id or role=owner in tenant_users) -> allow
    - rop (role=rop in tenant_users) -> allow ONLY for their tenant
    - manager -> forbidden
    """
    from sqlalchemy import text
    
    user_id = current_user.id
    user_email = getattr(current_user, "email", "unknown")
    
    # 1) Admin can access any tenant
    if getattr(current_user, "is_admin", False):
        print(f"[ACCESS] admin user_id={user_id} allowed for tenant_id={tenant_id}")
        return "admin"
    
    # 2) Check tenant-specific role with fallback for DB issues
    role = None
    try:
        role = await crud.get_tenant_user_role(db, tenant_id, user_id)
    except Exception as e:
        error_str = str(e)
        error_name = type(e).__name__
        print(f"[WARN] get_tenant_user_role failed for tenant {tenant_id}, user {user_id}: {error_name}: {e}")
        
        # Fallback: check tenant_users table directly with raw SQL
        # Handle both SQLite (OperationalError) and PostgreSQL (ProgrammingError)
        if any(x in error_name for x in ["OperationalError", "ProgrammingError"]) or \
           any(x in error_str for x in ["no such column", "column", "does not exist", "UndefinedColumn"]):
            try:
                await db.rollback()
            except Exception:
                pass
            try:
                # Check if user is default_owner using raw SQL
                result = await db.execute(text(
                    "SELECT default_owner_user_id FROM tenants WHERE id = :tid"
                ), {"tid": tenant_id})
                row = result.fetchone()
                if row and row[0] == user_id:
                    print(f"[ACCESS] fallback: user_id={user_id} is default_owner for tenant_id={tenant_id}")
                    return "owner"
                
                # Check tenant_users table
                result = await db.execute(text(
                    "SELECT role FROM tenant_users WHERE tenant_id = :tid AND user_id = :uid"
                ), {"tid": tenant_id, "uid": user_id})
                row = result.fetchone()
                if row:
                    role = (row[0] or "").strip().lower()
                    if role == "member":
                        role = "manager"
            except Exception as e2:
                print(f"[ERROR] Fallback raw SQL also failed: {e2}")
    
    # 3) Check role permissions
    if role == "owner":
        print(f"[ACCESS] owner user_id={user_id} allowed for tenant_id={tenant_id}")
        return "owner"
    
    if role == "rop":
        print(f"[ACCESS] rop user_id={user_id} allowed for tenant_id={tenant_id}")
        return "rop"
    
    if role == "manager":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: role=manager cannot access tenant settings. Contact your admin."
        )
    
    # No role found
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Forbidden: user {user_email} has no access to tenant {tenant_id}. Required: admin, owner, or rop role."
    )


# ========== Tenant Settings ==========

async def _build_tenant_settings_response(db: AsyncSession, tenant_id: int, tenant) -> TenantSettingsResponse:
    """Build a complete TenantSettingsResponse with all fields and safe defaults."""
    # Settings block
    ai_prompt_raw = getattr(tenant, "ai_prompt", None) or ""
    settings = TenantSettingsBlock(
        whatsapp_source=getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
        ai_enabled_global=getattr(tenant, "ai_enabled_global", True) if hasattr(tenant, "ai_enabled_global") else True,
        ai_prompt=ai_prompt_raw,
        ai_prompt_len=len(ai_prompt_raw),
        ai_after_lead_submitted_behavior=getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
        amocrm_base_domain=getattr(tenant, "amocrm_base_domain", None),
    )
    
    # WhatsApp snapshot
    try:
        whatsapp_snapshot_dict = await crud.get_chatflow_binding_snapshot(db, tenant_id)
        whatsapp_snapshot = ChatFlowBindingSnapshot(
            binding_exists=whatsapp_snapshot_dict.get("binding_exists", False),
            is_active=whatsapp_snapshot_dict.get("is_active", False),
            accounts_count=whatsapp_snapshot_dict.get("accounts_count", 0) if "accounts_count" in whatsapp_snapshot_dict else (1 if whatsapp_snapshot_dict.get("binding_exists") else 0),
            phone_number=whatsapp_snapshot_dict.get("phone_number"),
            chatflow_instance_id=whatsapp_snapshot_dict.get("chatflow_instance_id"),
            chatflow_token_masked=whatsapp_snapshot_dict.get("chatflow_token_masked"),
        )
    except Exception as e:
        print(f"[WARN] Failed to get whatsapp snapshot for tenant {tenant_id}: {e}")
        whatsapp_snapshot = ChatFlowBindingSnapshot()
    
    # AmoCRM snapshot
    try:
        integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
        if integration:
            expires_at_str = None
            if integration.token_expires_at:
                try:
                    expires_at_str = integration.token_expires_at.isoformat()
                except Exception:
                    expires_at_str = str(integration.token_expires_at)
            amocrm_snapshot = AmoCRMSnapshot(
                connected=bool(integration.access_token and integration.is_active),
                base_domain=integration.base_domain,
                expires_at=expires_at_str,
            )
        else:
            amocrm_snapshot = AmoCRMSnapshot()
    except Exception as e:
        print(f"[WARN] Failed to get amocrm snapshot for tenant {tenant_id}: {e}")
        amocrm_snapshot = AmoCRMSnapshot()
    
    # Mappings snapshot
    try:
        pipeline_mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
        field_mappings = await crud.list_field_mappings(db, tenant_id, "amocrm")
        mappings_snapshot = MappingsSnapshot(
            pipeline_count=len(pipeline_mappings) if pipeline_mappings else 0,
            field_count=len(field_mappings) if field_mappings else 0,
        )
    except Exception as e:
        print(f"[WARN] Failed to get mappings for tenant {tenant_id}: {e}")
        mappings_snapshot = MappingsSnapshot()
    
    return TenantSettingsResponse(
        ok=True,
        tenant_id=tenant_id,
        tenant_name=tenant.name or "",
        settings=settings,
        whatsapp=whatsapp_snapshot,
        amocrm=amocrm_snapshot,
        mappings=mappings_snapshot,
    )


async def _get_tenant_with_fallback(db: AsyncSession, tenant_id: int) -> dict | None:
    """Get tenant data with raw SQL fallback if ORM fails due to missing columns."""
    from sqlalchemy import text
    
    # First try ORM
    try:
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if tenant:
            return {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "is_active": tenant.is_active,
                "ai_prompt": getattr(tenant, "ai_prompt", None) or "",
                "ai_enabled": getattr(tenant, "ai_enabled", True),
                "whatsapp_source": getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
                "ai_enabled_global": getattr(tenant, "ai_enabled_global", True),
                "ai_after_lead_submitted_behavior": getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
                "amocrm_base_domain": getattr(tenant, "amocrm_base_domain", None),
            }
        return None
    except Exception as e:
        error_name = type(e).__name__
        error_str = str(e)
        # Handle both SQLite (OperationalError) and PostgreSQL (ProgrammingError) column errors
        if any(x in error_name for x in ["OperationalError", "ProgrammingError"]) or \
           any(x in error_str for x in ["no such column", "column", "does not exist", "UndefinedColumn"]):
            print(f"[WARN] ORM failed for tenant {tenant_id} ({error_name}), falling back to raw SQL")
            try:
                await db.rollback()
            except Exception:
                pass
        else:
            raise
    
    # Fallback to raw SQL with minimal columns
    try:
        result = await db.execute(text("SELECT id, name, slug, is_active, created_at FROM tenants WHERE id = :tid"), {"tid": tenant_id})
        row = result.fetchone()
        if row:
            print(f"[INFO] Got tenant {tenant_id} via raw SQL fallback")
            return {
                "id": row[0],
                "name": row[1],
                "slug": row[2],
                "is_active": row[3],
                "ai_prompt": "",
                "ai_enabled": True,
                "whatsapp_source": "chatflow",
                "ai_enabled_global": True,
                "ai_after_lead_submitted_behavior": "polite_close",
                "amocrm_base_domain": None,
            }
    except Exception as e2:
        print(f"[ERROR] Raw SQL also failed for tenant {tenant_id}: {e2}")
    
    return None


@router.get("/tenants/{tenant_id}/settings", summary="Настройки tenant для Universal Admin")
async def get_tenant_settings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить настройки tenant со снапшотами WhatsApp и AmoCRM.
    ALWAYS returns complete structure with ok:true/false.
    """
    try:
        user_role = await _require_tenant_access(db, tenant_id, current_user)
        print(f"[INFO] get_tenant_settings: user_role={user_role}, tenant_id={tenant_id}")
    except HTTPException as e:
        return _safe_json_error(e.detail, e.status_code)
    except Exception as e:
        print(f"[ERROR] get_tenant_settings access check failed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _safe_json_error(f"Access check failed: {type(e).__name__}", 403)
    
    try:
        tenant_data = await _get_tenant_with_fallback(db, tenant_id)
        if not tenant_data:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "detail": f"Tenant {tenant_id} not found"}
            )
        
        # Build response using tenant_data dict
        print(f"[INFO] get_tenant_settings: tenant_id={tenant_id}, name={tenant_data.get('name')}")
        
        # Create a simple object-like wrapper for tenant_data
        class TenantWrapper:
            def __init__(self, data):
                for k, v in data.items():
                    setattr(self, k, v)
        
        tenant = TenantWrapper(tenant_data)
        response = await _build_tenant_settings_response(db, tenant_id, tenant)
        return response
        
    except Exception as e:
        print(f"[ERROR] get_tenant_settings failed for tenant {tenant_id}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _safe_json_error(f"Failed to load settings: {type(e).__name__}")


@router.patch("/tenants/{tenant_id}/settings", summary="Обновить настройки tenant")
async def update_tenant_settings(
    tenant_id: int,
    body: TenantSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Обновить настройки tenant.
    Поддерживает: whatsapp_source, ai_enabled_global, ai_prompt, ai_after_lead_submitted_behavior, amocrm_base_domain.
    """
    try:
        user_role = await _require_tenant_access(db, tenant_id, current_user)
        print(f"[INFO] update_tenant_settings: user_role={user_role}, tenant_id={tenant_id}")
    except HTTPException as e:
        return _safe_json_error(e.detail, e.status_code)
    except Exception as e:
        print(f"[ERROR] update_tenant_settings access check failed: {type(e).__name__}: {e}")
        return _safe_json_error(f"Access check failed: {type(e).__name__}", 403)
    
    # Prepare update data
    update_data = body.model_dump(exclude_unset=True)
    print(f"[INFO] update_tenant_settings: tenant_id={tenant_id}, fields to update: {list(update_data.keys())}")
    
    # Use raw SQL update for maximum compatibility
    # This avoids ORM issues when columns might not exist in older schema
    from sqlalchemy import text
    
    try:
        # Build UPDATE query dynamically
        updates = []
        params = {"tid": tenant_id}
        
        # Map request fields to DB columns
        field_mapping = {
            "whatsapp_source": "whatsapp_source",
            "ai_enabled_global": "ai_enabled_global",
            "ai_prompt": "ai_prompt",
            "ai_after_lead_submitted_behavior": "ai_after_lead_submitted_behavior",
            "amocrm_base_domain": "amocrm_base_domain",
        }
        
        for req_field, db_field in field_mapping.items():
            if req_field in update_data:
                value = update_data[req_field]
                # Normalize amocrm_base_domain
                if req_field == "amocrm_base_domain" and value:
                    value = _normalize_amocrm_domain(value)
                updates.append(f"{db_field} = :{db_field}")
                params[db_field] = value
        
        if updates:
            # Try update with all fields first
            try:
                query = f"UPDATE tenants SET {', '.join(updates)} WHERE id = :tid"
                await db.execute(text(query), params)
                await db.commit()
                print(f"[INFO] update_tenant_settings: updated tenant {tenant_id} with {len(updates)} fields")
            except Exception as e:
                error_str = str(e).lower()
                # If specific column doesn't exist, try updating only core fields
                if "column" in error_str or "does not exist" in error_str or "no such column" in error_str:
                    print(f"[WARN] Some columns missing, trying core fields only: {e}")
                    try:
                        await db.rollback()
                    except Exception:
                        pass
                    
                    # Try only ai_prompt which should always exist
                    if "ai_prompt" in update_data:
                        core_query = "UPDATE tenants SET ai_prompt = :ai_prompt WHERE id = :tid"
                        core_params = {"tid": tenant_id, "ai_prompt": update_data["ai_prompt"]}
                        await db.execute(text(core_query), core_params)
                        await db.commit()
                        print(f"[INFO] update_tenant_settings: updated ai_prompt only for tenant {tenant_id}")
                else:
                    raise
        
        # Fetch updated tenant and return
        tenant_data = await _get_tenant_with_fallback(db, tenant_id)
        if not tenant_data:
            return JSONResponse(status_code=404, content={"ok": False, "detail": "Tenant not found"})
        
        class TenantWrapper:
            def __init__(self, data):
                for k, v in data.items():
                    setattr(self, k, v)
        
        response = await _build_tenant_settings_response(db, tenant_id, TenantWrapper(tenant_data))
        return response
        
    except Exception as e:
        error_name = type(e).__name__
        print(f"[ERROR] update_tenant_settings failed for tenant {tenant_id}: {error_name}: {e}")
        traceback.print_exc()
        
        try:
            await db.rollback()
        except Exception:
            pass
        
        return _safe_json_error(f"Failed to update settings: {error_name}")


# ========== AmoCRM Integration ==========

@router.get("/tenants/{tenant_id}/amocrm/auth-url", summary="URL для OAuth в amoCRM")
async def get_amocrm_auth_url(
    tenant_id: int,
    base_domain: str = Query(None, description="Домен amoCRM (опционально если уже сохранён в настройках), например baxa.amocrm.ru"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Сформировать URL для OAuth авторизации в amoCRM.
    
    - Если base_domain передан в query — используется он
    - Иначе берётся из tenant.amocrm_base_domain
    - Если нигде не задан — возвращается 422 с понятной ошибкой
    - Домен валидируется: только *.amocrm.ru или *.kommo.com
    
    Returns: {ok: true, auth_url: "...", base_domain: "..."} or {ok: false, detail: "...", code: "..."}
    """
    import re
    
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    print(f"[INFO] get_amocrm_auth_url: tenant_id={tenant_id}, base_domain_query={base_domain}")
    
    # Step 1: Determine and normalize base_domain FIRST (before checking ENV)
    domain = (base_domain or "").strip()
    if not domain:
        try:
            tenant_data = await _get_tenant_with_fallback(db, tenant_id)
            if tenant_data:
                domain = (tenant_data.get("amocrm_base_domain") or "").strip()
        except Exception as e:
            print(f"[WARN] Failed to get tenant for domain: {e}")
    
    # Normalize domain - extract host from any URL format
    # Accepts: "company.amocrm.ru", "https://company.amocrm.ru", "https://company.amocrm.ru/leads/pipeline"
    original_domain = domain
    domain = _normalize_amocrm_domain(domain)
    
    if original_domain and original_domain != domain:
        print(f"[INFO] Normalized domain: '{original_domain}' -> '{domain}'")
    
    # Step 2: Validate domain format BEFORE checking ENV
    if not domain:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "detail": "base_domain is required. Example: company.amocrm.ru or company.kommo.com",
                "code": "BASE_DOMAIN_REQUIRED"
            }
        )
    
    # Validate domain format
    if not re.match(r"^[\w\-]+\.(amocrm\.ru|kommo\.com)$", domain, re.IGNORECASE):
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "detail": f"Invalid base_domain format: '{domain}'. Must end with .amocrm.ru or .kommo.com (e.g. company.amocrm.ru)",
                "code": "INVALID_DOMAIN_FORMAT"
            }
        )
    
    # Step 3: Now check ENV variables
    from app.core.config import get_settings
    settings = get_settings()
    amo_client_id = getattr(settings, "amo_client_id", None)
    amo_client_secret = getattr(settings, "amo_client_secret", None)
    amo_redirect_url = getattr(settings, "amo_redirect_url", None)
    
    missing_env = []
    if not amo_client_id:
        missing_env.append("AMO_CLIENT_ID")
    if not amo_client_secret:
        missing_env.append("AMO_CLIENT_SECRET")
    if not amo_redirect_url:
        missing_env.append("AMO_REDIRECT_URL")
    
    if missing_env:
        print(f"[ERROR] AmoCRM OAuth ENV missing: {missing_env}")
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "detail": f"Server configuration error: missing {', '.join(missing_env)}. Contact administrator.",
                "code": "ENV_MISSING"
            }
        )
    
    # Domain was already validated above, proceed to build auth URL
    try:
        url = amocrm_service.build_auth_url(tenant_id, domain)
        if not url:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "detail": "Failed to build auth URL. Check server configuration.",
                    "code": "BUILD_URL_FAILED"
                }
            )
    except Exception as e:
        print(f"[ERROR] build_auth_url failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": f"Failed to build auth URL: {type(e).__name__}"}
        )
    
    # Save domain to tenant settings for future use
    try:
        await crud.update_tenant(db, tenant_id, amocrm_base_domain=domain)
    except Exception as e:
        print(f"[WARN] Failed to save amocrm_base_domain: {e}")
    
    print(f"[INFO] AmoCRM auth URL generated for tenant {tenant_id}, domain={domain}")
    return {"ok": True, "auth_url": url, "base_domain": domain}


@router.post("/tenants/{tenant_id}/amocrm/callback", summary="Обмен code на токены amoCRM")
async def amocrm_callback(
    tenant_id: int,
    body: AmoCRMCallbackBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обменять code на access_token/refresh_token и сохранить."""
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        result = await amocrm_service.exchange_code_for_tokens(db, tenant_id, body.base_domain, body.code)
        if not result:
            return JSONResponse(status_code=400, content={"ok": False, "detail": "Failed to exchange code for tokens. Check server logs."})
        # Also save base_domain to tenant settings
        await crud.update_tenant(db, tenant_id, amocrm_base_domain=body.base_domain)
        return {"ok": True, **result}
    except Exception as e:
        print(f"[ERROR] amocrm_callback failed for tenant {tenant_id}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Token exchange failed: {type(e).__name__}"})


@router.get("/tenants/{tenant_id}/amocrm/status", summary="Статус интеграции amoCRM")
async def get_amocrm_status(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Статус интеграции amoCRM (без токенов). Returns same shape as amocrm block in /settings."""
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
        if not integration:
            return {
                "ok": True,
                "connected": False,
                "base_domain": None,
                "expires_at": None
            }
        
        expires_at_str = None
        if integration.token_expires_at:
            try:
                expires_at_str = integration.token_expires_at.isoformat()
            except Exception:
                expires_at_str = str(integration.token_expires_at)
        
        return {
            "ok": True,
            "connected": bool(integration.access_token and integration.is_active),
            "base_domain": integration.base_domain,
            "expires_at": expires_at_str
        }
    except Exception as e:
        print(f"[ERROR] get_amocrm_status failed for tenant {tenant_id}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Failed to get status: {type(e).__name__}"})


@router.post("/tenants/{tenant_id}/amocrm/refresh", summary="Принудительно обновить токены amoCRM")
async def refresh_amocrm_tokens(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Принудительно обновить токены amoCRM."""
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        client = await amocrm_service.get_amocrm_client(db, tenant_id)
        if not client:
            return JSONResponse(status_code=400, content={"ok": False, "detail": "AmoCRM integration not active or not connected"})
        refreshed = await client._refresh_if_needed()
        return {"ok": True, "refreshed": refreshed}
    except Exception as e:
        print(f"[ERROR] refresh_amocrm_tokens failed for tenant {tenant_id}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Refresh failed: {type(e).__name__}"})


@router.post("/tenants/{tenant_id}/amocrm/disconnect", summary="Отключить интеграцию amoCRM")
async def disconnect_amocrm(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Деактивировать интеграцию amoCRM."""
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        result = await crud.deactivate_tenant_integration(db, tenant_id, "amocrm")
        return {"ok": result}
    except Exception as e:
        print(f"[ERROR] disconnect_amocrm failed for tenant {tenant_id}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Disconnect failed: {type(e).__name__}"})


# ========== AmoCRM Pipeline/Stage Discovery ==========

@router.get("/tenants/{tenant_id}/amocrm/pipelines", summary="Список воронок amoCRM", tags=["AmoCRM Discovery"])
async def get_amocrm_pipelines(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить список воронок (pipelines) из подключённого AmoCRM.
    
    Требуется активная интеграция AmoCRM.
    
    Returns:
        {ok: true, pipelines: [{id, name, is_main, sort}, ...]}
    """
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        client = await amocrm_service.get_amocrm_client(db, tenant_id)
        if not client:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "detail": "AmoCRM integration not connected. Please connect AmoCRM first.",
                    "code": "NOT_CONNECTED"
                }
            )
        
        pipelines = await client.get_pipelines()
        if pipelines is None:
            return JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "detail": "Failed to fetch pipelines from AmoCRM. Check connection or try again.",
                    "code": "AMO_API_ERROR"
                }
            )
        
        print(f"[INFO] get_amocrm_pipelines: tenant_id={tenant_id}, found {len(pipelines)} pipelines")
        return {"ok": True, "pipelines": pipelines}
        
    except Exception as e:
        print(f"[ERROR] get_amocrm_pipelines failed for tenant {tenant_id}: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": f"Failed to fetch pipelines: {type(e).__name__}"}
        )


@router.get("/tenants/{tenant_id}/amocrm/pipelines/{pipeline_id}/stages", summary="Стадии воронки amoCRM", tags=["AmoCRM Discovery"])
async def get_amocrm_pipeline_stages(
    tenant_id: int,
    pipeline_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить стадии (statuses) конкретной воронки из AmoCRM.
    
    Returns:
        {ok: true, stages: [{id, name, sort, is_won, is_lost, color, type}, ...]}
    
    Stage types:
        - type=0: обычная стадия
        - type=1: Успешно реализовано (won)
        - type=2: Закрыто и не реализовано (lost)
    """
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        client = await amocrm_service.get_amocrm_client(db, tenant_id)
        if not client:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "detail": "AmoCRM integration not connected",
                    "code": "NOT_CONNECTED"
                }
            )
        
        stages = await client.get_pipeline_stages(pipeline_id)
        if stages is None:
            return JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "detail": f"Failed to fetch stages for pipeline {pipeline_id} from AmoCRM",
                    "code": "AMO_API_ERROR"
                }
            )
        
        print(f"[INFO] get_amocrm_pipeline_stages: tenant_id={tenant_id}, pipeline_id={pipeline_id}, found {len(stages)} stages")
        return {"ok": True, "pipeline_id": pipeline_id, "stages": stages}
        
    except Exception as e:
        print(f"[ERROR] get_amocrm_pipeline_stages failed: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": f"Failed to fetch stages: {type(e).__name__}"}
        )


@router.get("/tenants/{tenant_id}/amocrm/pipeline-snapshot", summary="Полная структура воронок и стадий", tags=["AmoCRM Discovery"])
async def get_amocrm_pipeline_snapshot(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить полную структуру воронок и их стадий за один запрос.
    Удобно для UI выбора стадий при маппинге.
    
    Returns:
        {
            ok: true,
            pipelines: [{id, name, is_main, sort}, ...],
            stages_by_pipeline: {
                "pipeline_id": [{id, name, sort, is_won, is_lost, color}, ...]
            }
        }
    """
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        client = await amocrm_service.get_amocrm_client(db, tenant_id)
        if not client:
            return JSONResponse(
                status_code=400,
                content={
                    "ok": False,
                    "detail": "AmoCRM integration not connected",
                    "code": "NOT_CONNECTED"
                }
            )
        
        snapshot = await client.get_pipeline_snapshot()
        if snapshot is None:
            return JSONResponse(
                status_code=502,
                content={
                    "ok": False,
                    "detail": "Failed to fetch pipeline structure from AmoCRM",
                    "code": "AMO_API_ERROR"
                }
            )
        
        pipelines = snapshot.get("pipelines", [])
        stages_by_pipeline = snapshot.get("stages_by_pipeline", {})
        total_stages = sum(len(s) for s in stages_by_pipeline.values())
        print(f"[INFO] get_amocrm_pipeline_snapshot: tenant_id={tenant_id}, {len(pipelines)} pipelines, {total_stages} stages total")
        
        return {
            "ok": True,
            "pipelines": pipelines,
            "stages_by_pipeline": stages_by_pipeline
        }
        
    except Exception as e:
        print(f"[ERROR] get_amocrm_pipeline_snapshot failed: {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=500,
            content={"ok": False, "detail": f"Failed to fetch snapshot: {type(e).__name__}"}
        )


# ========== Combined Mapping Endpoint ==========

@router.get("/tenants/{tenant_id}/amocrm/mapping", summary="Все маппинги amoCRM (pipeline + field)")
async def get_all_mappings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Комбинированный endpoint: возвращает и pipeline-mapping, и field-mapping."""
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception:
        return JSONResponse(status_code=403, content={"ok": False, "detail": "Access denied"})
    
    try:
        pipeline_mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
        field_mappings = await crud.list_field_mappings(db, tenant_id, "amocrm")
        
        return {
            "ok": True,
            "pipeline_mappings": [
                {"id": m.id, "stage_key": m.stage_key, "stage_id": m.stage_id, "pipeline_id": m.pipeline_id}
                for m in pipeline_mappings
            ],
            "field_mappings": [
                {"id": m.id, "field_key": m.field_key, "amo_field_id": m.amo_field_id, "entity_type": m.entity_type}
                for m in field_mappings
            ],
        }
    except Exception as e:
        print(f"[ERROR] get_all_mappings failed: {type(e).__name__}: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "detail": f"Failed to get mappings: {type(e).__name__}"})


# ========== Pipeline Mappings ==========

@router.get("/tenants/{tenant_id}/amocrm/pipeline-mapping", response_model=list[PipelineMappingResponse], summary="Маппинг стадий amoCRM")
async def get_pipeline_mappings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список маппингов stage_key -> stage_id."""
    await _require_tenant_access(db, tenant_id, current_user)
    mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
    return [PipelineMappingResponse.model_validate(m) for m in mappings]


@router.put("/tenants/{tenant_id}/amocrm/pipeline-mapping", summary="Bulk upsert маппингов стадий")
async def update_pipeline_mappings(
    tenant_id: int,
    body: PipelineMappingBulkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk upsert маппингов stage_key -> stage_id."""
    await _require_tenant_access(db, tenant_id, current_user)
    results = []
    for item in body.mappings:
        m = await crud.upsert_pipeline_mapping(
            db,
            tenant_id=tenant_id,
            provider="amocrm",
            stage_key=item.stage_key,
            stage_id=item.stage_id,
            pipeline_id=item.pipeline_id,
            is_active=item.is_active,
        )
        results.append(PipelineMappingResponse.model_validate(m))
    return {"ok": True, "count": len(results), "mappings": results}


# ========== Field Mappings ==========

@router.get("/tenants/{tenant_id}/amocrm/field-mapping", response_model=list[FieldMappingResponse], summary="Маппинг полей amoCRM")
async def get_field_mappings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Список маппингов field_key -> amo_field_id."""
    await _require_tenant_access(db, tenant_id, current_user)
    mappings = await crud.list_field_mappings(db, tenant_id, "amocrm")
    return [FieldMappingResponse.model_validate(m) for m in mappings]


@router.put("/tenants/{tenant_id}/amocrm/field-mapping", summary="Bulk upsert маппингов полей")
async def update_field_mappings(
    tenant_id: int,
    body: FieldMappingBulkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Bulk upsert маппингов field_key -> amo_field_id."""
    await _require_tenant_access(db, tenant_id, current_user)
    results = []
    for item in body.mappings:
        m = await crud.upsert_field_mapping(
            db,
            tenant_id=tenant_id,
            provider="amocrm",
            field_key=item.field_key,
            entity_type=item.entity_type,
            amo_field_id=item.amo_field_id,
            is_active=item.is_active,
        )
        results.append(FieldMappingResponse.model_validate(m))
    return {"ok": True, "count": len(results), "mappings": results}


# ========== Mute from Lead ==========

@router.post("/leads/{lead_id}/mute", response_model=LeadMuteResponse, summary="Mute/unmute чат из карточки лида")
async def mute_lead_chat(
    lead_id: int,
    body: LeadMuteBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mute/unmute чат для лида. Требует lead.tenant_id.
    Ищет conversation по lead.bot_user_id и ставит is_enabled=False в chat_ai_states.
    """
    result = await crud.mute_chat_for_lead(db, lead_id, body.muted, muted_by_user_id=current_user.id)
    if not result.get("ok"):
        return LeadMuteResponse(ok=False, error=result.get("error"))
    return LeadMuteResponse(
        ok=True,
        muted=result.get("muted"),
        channel=result.get("channel"),
        external_id=result.get("external_id"),
    )


# ========== Diagnostics: Tenant Snapshot ==========

@router.get("/diagnostics/tenant/{tenant_id}/snapshot", summary="Снапшот состояния tenant")
async def tenant_snapshot(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner_or_rop),
):
    """
    Диагностика: настройки tenant, привязка WhatsApp, amoCRM, количество маппингов.
    """
    try:
        tenant_data = await _get_tenant_with_fallback(db, tenant_id)
        if not tenant_data:
            return JSONResponse(status_code=404, content={"ok": False, "detail": "Tenant not found"})
        
        # WhatsApp accounts
        try:
            wa_accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
            wa_binding = bool(wa_accounts)
            wa_active = any(a.is_active for a in wa_accounts) if wa_accounts else False
        except Exception:
            wa_accounts = []
            wa_binding = False
            wa_active = False
        
        # AmoCRM
        try:
            amo_integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
            amo_connected = bool(amo_integration and amo_integration.is_active and amo_integration.access_token)
        except Exception:
            amo_integration = None
            amo_connected = False
        
        # Mappings count
        try:
            pipeline_mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
            field_mappings = await crud.list_field_mappings(db, tenant_id, "amocrm")
        except Exception:
            pipeline_mappings = []
            field_mappings = []
        
        # Get first WhatsApp account details if exists
        wa_phone = None
        wa_instance_id = None
        wa_token_masked = None
        wa_token_present = False
        wa_instance_present = False
        wa_credentials_ok = False
        if wa_accounts:
            first_wa = wa_accounts[0]
            wa_phone = getattr(first_wa, "phone_number", None)
            wa_instance_id = getattr(first_wa, "chatflow_instance_id", None)
            wa_token_masked = getattr(first_wa, "chatflow_token_masked", None)
            # Check if credentials are actually configured
            raw_token = getattr(first_wa, "chatflow_token", None) or ""
            raw_instance = getattr(first_wa, "chatflow_instance_id", None) or ""
            wa_token_present = bool(raw_token.strip())
            wa_instance_present = bool(raw_instance.strip())
            wa_credentials_ok = wa_token_present and wa_instance_present
        
        # AI prompt details
        ai_prompt_raw = tenant_data.get("ai_prompt") or ""
        ai_prompt_preview = ai_prompt_raw[:100] + "..." if len(ai_prompt_raw) > 100 else ai_prompt_raw
        
        return {
            "ok": True,
            "tenant_id": tenant_id,
            "tenant_name": tenant_data.get("name", ""),
            "settings": {
                "whatsapp_source": tenant_data.get("whatsapp_source", "chatflow"),
                "ai_enabled_global": tenant_data.get("ai_enabled_global", True),
                "ai_enabled": tenant_data.get("ai_enabled", True),
                "ai_prompt_len": len(ai_prompt_raw),
                "ai_prompt_preview": ai_prompt_preview,
                "ai_prompt_is_set": bool(ai_prompt_raw.strip()),
                "ai_after_lead_submitted_behavior": tenant_data.get("ai_after_lead_submitted_behavior", "polite_close"),
                "amocrm_base_domain": tenant_data.get("amocrm_base_domain"),
                "webhook_key": tenant_data.get("webhook_key"),
            },
            "whatsapp": {
                "binding_exists": wa_binding,
                "is_active": wa_active,
                "accounts_count": len(wa_accounts) if wa_accounts else 0,
                "phone_number": wa_phone,
                "chatflow_instance_id": wa_instance_id,
                "chatflow_token_masked": wa_token_masked,
                "chatflow_token_present": wa_token_present,
                "chatflow_instance_present": wa_instance_present,
                "chatflow_credentials_ok": wa_credentials_ok,
                "chatflow_ready": wa_binding and wa_active and wa_credentials_ok,
            },
            "amocrm": {
                "connected": amo_connected,
                "is_active": amo_integration.is_active if amo_integration else False,
                "base_domain": amo_integration.base_domain if amo_integration else None,
                "base_domain_from_settings": tenant_data.get("amocrm_base_domain"),
                "token_expires_at": amo_integration.token_expires_at.isoformat() if amo_integration and amo_integration.token_expires_at else None,
            },
            "mappings": {
                "pipeline_count": len(pipeline_mappings) if pipeline_mappings else 0,
                "field_count": len(field_mappings) if field_mappings else 0,
            },
        }
    except Exception as e:
        print(f"[ERROR] tenant_snapshot failed for tenant {tenant_id}: {e}")
        traceback.print_exc()
        return _safe_json_error(f"Failed to get snapshot: {type(e).__name__}")


# ========== Debug Endpoint for Access Troubleshooting ==========

@router.get("/tenants/{tenant_id}/settings/debug", summary="Debug access control for tenant settings", tags=["Diagnostics"])
async def tenant_settings_debug(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Debug endpoint to help troubleshoot access control issues.
    Returns detailed information about the current user's access to the requested tenant.
    
    This endpoint does NOT require tenant access - it just reports what access the user would have.
    """
    from sqlalchemy import text
    
    user_id = current_user.id
    user_email = getattr(current_user, "email", "unknown")
    is_admin = getattr(current_user, "is_admin", False)
    
    result = {
        "ok": True,
        "debug": {
            "current_user": {
                "id": user_id,
                "email": user_email,
                "is_admin": is_admin,
            },
            "requested_tenant_id": tenant_id,
            "access_decision": {
                "is_admin": is_admin,
                "is_owner": False,
                "is_rop": False,
                "is_manager": False,
                "has_tenant_access": False,
                "allowed": False,
                "reason": "",
            },
            "tenant_info": None,
            "user_role_in_tenant": None,
        }
    }
    
    # Check if admin
    if is_admin:
        result["debug"]["access_decision"]["allowed"] = True
        result["debug"]["access_decision"]["has_tenant_access"] = True
        result["debug"]["access_decision"]["reason"] = "User is admin (is_admin=True), can access any tenant"
    
    # Check tenant exists and get user's role
    try:
        # Try to get tenant info via raw SQL to avoid column issues
        tenant_result = await db.execute(text(
            "SELECT id, name, slug, is_active, default_owner_user_id FROM tenants WHERE id = :tid"
        ), {"tid": tenant_id})
        tenant_row = tenant_result.fetchone()
        
        if tenant_row:
            result["debug"]["tenant_info"] = {
                "id": tenant_row[0],
                "name": tenant_row[1],
                "slug": tenant_row[2],
                "is_active": tenant_row[3],
                "default_owner_user_id": tenant_row[4],
            }
            
            # Check if user is default owner
            if tenant_row[4] == user_id:
                result["debug"]["access_decision"]["is_owner"] = True
                result["debug"]["access_decision"]["allowed"] = True
                result["debug"]["access_decision"]["has_tenant_access"] = True
                result["debug"]["access_decision"]["reason"] = "User is default_owner_user_id of tenant"
        else:
            result["debug"]["access_decision"]["reason"] = f"Tenant {tenant_id} not found"
            result["debug"]["tenant_info"] = {"error": "Tenant not found"}
        
        # Check tenant_users table
        tu_result = await db.execute(text(
            "SELECT role FROM tenant_users WHERE tenant_id = :tid AND user_id = :uid"
        ), {"tid": tenant_id, "uid": user_id})
        tu_row = tu_result.fetchone()
        
        if tu_row:
            role = (tu_row[0] or "").strip().lower()
            if role == "member":
                role = "manager"
            result["debug"]["user_role_in_tenant"] = role
            
            if role == "owner":
                result["debug"]["access_decision"]["is_owner"] = True
                result["debug"]["access_decision"]["allowed"] = True
                result["debug"]["access_decision"]["has_tenant_access"] = True
                result["debug"]["access_decision"]["reason"] = "User has role=owner in tenant_users"
            elif role == "rop":
                result["debug"]["access_decision"]["is_rop"] = True
                result["debug"]["access_decision"]["allowed"] = True
                result["debug"]["access_decision"]["has_tenant_access"] = True
                result["debug"]["access_decision"]["reason"] = "User has role=rop in tenant_users"
            elif role == "manager":
                result["debug"]["access_decision"]["is_manager"] = True
                result["debug"]["access_decision"]["allowed"] = False
                result["debug"]["access_decision"]["reason"] = "User has role=manager, cannot access admin settings"
        else:
            if not result["debug"]["access_decision"]["allowed"]:
                result["debug"]["user_role_in_tenant"] = None
                if not is_admin:
                    result["debug"]["access_decision"]["reason"] = f"User {user_email} has no role in tenant {tenant_id} and is not admin"
                    
    except Exception as e:
        result["debug"]["error"] = f"Failed to check access: {type(e).__name__}: {str(e)[:200]}"
    
    return result


# ========== Self-Check Endpoint ==========

@router.post("/tenants/{tenant_id}/self-check", summary="Полная проверка конфигурации tenant")
async def tenant_self_check(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Полная самопроверка tenant: таблицы, настройки, привязки, amoCRM.
    Возвращает массив checks с ok/error и причинами.
    """
    try:
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"ok": False, "detail": e.detail})
    except Exception as e:
        return JSONResponse(status_code=403, content={"ok": False, "detail": f"Access check failed: {type(e).__name__}"})
    
    checks = []
    overall_ok = True
    
    # 1) Check tenant exists (use fallback to avoid ORM errors)
    tenant_data = await _get_tenant_with_fallback(db, tenant_id)
    if not tenant_data:
        return {"ok": False, "checks": [{"check": "tenant_exists", "ok": False, "error": "Tenant not found"}]}
    
    # Create a wrapper for attribute access
    class TenantWrapper:
        def __init__(self, data):
            for k, v in data.items():
                setattr(self, k, v)
    tenant = TenantWrapper(tenant_data)
    
    if not tenant_data:
        return {"ok": False, "checks": [{"check": "tenant_exists", "ok": False, "error": "Tenant not found"}]}
    checks.append({"check": "tenant_exists", "ok": True, "detail": f"Tenant '{tenant.name}' exists"})
    
    # 2) Check tenant settings
    whatsapp_source = getattr(tenant, "whatsapp_source", "chatflow") or "chatflow"
    ai_enabled_global = getattr(tenant, "ai_enabled_global", True)
    ai_prompt_len = len(getattr(tenant, "ai_prompt", "") or "")
    checks.append({
        "check": "tenant_settings", 
        "ok": True, 
        "detail": f"whatsapp_source={whatsapp_source}, ai_enabled_global={ai_enabled_global}, ai_prompt_len={ai_prompt_len}"
    })
    
    # 3) Check WhatsApp binding (for chatflow mode)
    if whatsapp_source == "chatflow":
        wa_accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
        active_wa = [a for a in wa_accounts if a.is_active]
        if not active_wa:
            checks.append({
                "check": "whatsapp_binding", 
                "ok": False, 
                "error": "No active WhatsApp account. Go to Admin > Tenants > WhatsApp to bind."
            })
            overall_ok = False
        else:
            acc = active_wa[0]
            has_token = bool(getattr(acc, "chatflow_token", None))
            has_instance = bool(getattr(acc, "chatflow_instance_id", None))
            if not has_token or not has_instance:
                checks.append({
                    "check": "whatsapp_binding", 
                    "ok": False, 
                    "error": f"WhatsApp account missing chatflow_token or chatflow_instance_id"
                })
                overall_ok = False
            else:
                checks.append({
                    "check": "whatsapp_binding", 
                    "ok": True, 
                    "detail": f"WhatsApp bound: phone={acc.phone_number}, instance_id={acc.chatflow_instance_id[:8]}..."
                })
    
    # 4) Check AmoCRM integration (for amomarket mode)
    if whatsapp_source == "amomarket":
        integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
        if not integration or not integration.is_active:
            checks.append({
                "check": "amocrm_integration", 
                "ok": False, 
                "error": "AmoCRM not connected. Go to Admin > Tenants > amoCRM to connect."
            })
            overall_ok = False
        elif not integration.access_token:
            checks.append({
                "check": "amocrm_integration", 
                "ok": False, 
                "error": "AmoCRM has no access_token. Re-authorize via OAuth."
            })
            overall_ok = False
        else:
            from datetime import datetime
            expired = integration.token_expires_at and integration.token_expires_at < datetime.utcnow()
            if expired:
                checks.append({
                    "check": "amocrm_integration", 
                    "ok": False, 
                    "error": f"AmoCRM token expired at {integration.token_expires_at}. Trigger refresh."
                })
                overall_ok = False
            else:
                checks.append({
                    "check": "amocrm_integration", 
                    "ok": True, 
                    "detail": f"AmoCRM connected: domain={integration.base_domain}, expires={integration.token_expires_at}"
                })
        
        # 4b) Check pipeline mappings for amomarket
        mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
        unsorted_mapped = any(m.stage_key == "unprocessed" and m.stage_id for m in mappings)
        if not unsorted_mapped:
            checks.append({
                "check": "pipeline_mapping", 
                "ok": False, 
                "error": "No 'unprocessed' stage mapped. New leads cannot be created in amoCRM."
            })
            overall_ok = False
        else:
            checks.append({
                "check": "pipeline_mapping", 
                "ok": True, 
                "detail": f"{len(mappings)} stage mappings configured"
            })
    
    # 5) Check webhook_key
    webhook_key = getattr(tenant, "webhook_key", None)
    if not webhook_key:
        checks.append({
            "check": "webhook_key", 
            "ok": False, 
            "error": "Tenant has no webhook_key. Webhooks cannot be received."
        })
        overall_ok = False
    else:
        checks.append({
            "check": "webhook_key", 
            "ok": True, 
            "detail": f"webhook_key={webhook_key[:8]}..."
        })
    
    # 6) Dry-run: check AI can work
    if ai_enabled_global:
        from app.core.config import get_settings
        settings = get_settings()
        has_openai_key = bool(getattr(settings, "openai_api_key", None))
        if not has_openai_key:
            checks.append({
                "check": "ai_config", 
                "ok": False, 
                "error": "OPENAI_API_KEY not configured. AI replies will fail."
            })
            overall_ok = False
        else:
            checks.append({
                "check": "ai_config", 
                "ok": True, 
                "detail": "OpenAI API key configured"
            })
    
    return {
        "ok": overall_ok,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "whatsapp_source": whatsapp_source,
        "checks": checks,
    }


# ========== Public AmoCRM OAuth Callback ==========

@integrations_router.get("/amocrm/callback", include_in_schema=False, summary="OAuth callback от amoCRM")
async def amocrm_public_callback(
    code: str = Query(None, description="Authorization code from AmoCRM"),
    state: str = Query(None, description="State parameter (tenant_ID)"),
    referer: str = Query("", description="Referer header (optional)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Публичный callback для AmoCRM OAuth2.
    AmoCRM редиректит сюда с code и state=tenant_{id}.
    
    Если code/state не переданы — показываем понятную ошибку 400.
    """
    import os
    import re
    from fastapi.responses import HTMLResponse, RedirectResponse
    
    # Проверка: если нет code или state — это прямой заход, показываем ошибку
    if not code or not state:
        return HTMLResponse("""
        <html>
        <head><title>AmoCRM Callback</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>⚠️ Это callback URL для AmoCRM</h1>
            <p>Этот URL предназначен для автоматической обработки OAuth-авторизации AmoCRM.</p>
            <p>Чтобы подключить AmoCRM, перейдите в <strong>Админ-панель → Настройки тенанта → Интеграции</strong> и нажмите "Подключить AmoCRM".</p>
            <p style="color: #888; margin-top: 30px;">Ошибка: отсутствуют обязательные параметры (code, state).</p>
        </body>
        </html>
        """, status_code=400)
    
    # Извлекаем tenant_id и base_domain из state
    # Формат state: "tenant_{id}_{base_domain}" или старый "tenant_{id}"
    base_domain = None
    tenant_id = None
    
    # Новый формат: tenant_2_kanabahytzhan.amocrm.ru
    match_new = re.match(r"tenant_(\d+)_(.+)", state or "")
    if match_new:
        tenant_id = int(match_new.group(1))
        base_domain = match_new.group(2)
        print(f"[INFO] AmoCRM callback: state format=new, tenant_id={tenant_id}, base_domain={base_domain}")
    else:
        # Старый формат: tenant_2
        match_old = re.match(r"tenant_(\d+)", state or "")
        if match_old:
            tenant_id = int(match_old.group(1))
            print(f"[INFO] AmoCRM callback: state format=old, tenant_id={tenant_id}")
    
    if not tenant_id:
        return HTMLResponse(f"""
        <html>
        <head><title>Error</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>❌ Ошибка авторизации</h1>
            <p>Неверный параметр state: {state[:50] if state else '(пусто)'}</p>
            <p>Попробуйте подключить AmoCRM заново через админ-панель.</p>
        </body>
        </html>
        """, status_code=400)
    
    print(f"[INFO] AmoCRM callback: tenant_id={tenant_id}, code={code[:10]}...")
    
    # Если base_domain не из state, пробуем другие источники
    if not base_domain:
        # 1. Попробовать из tenant.amocrm_base_domain
        try:
            tenant_data = await _get_tenant_with_fallback(db, tenant_id)
            if tenant_data:
                base_domain = (tenant_data.get("amocrm_base_domain") or "").strip()
        except Exception as e:
            print(f"[WARN] Failed to get tenant for callback: {e}")
    
    if not base_domain:
        # 2. Fallback: из существующей интеграции
        try:
            integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
            if integration and integration.base_domain:
                base_domain = integration.base_domain
        except Exception as e:
            print(f"[WARN] Failed to get integration: {e}")
    
    if not base_domain and referer:
        # 3. Fallback: из referer (менее надежно)
        domain_match = re.search(r"https?://([^/]+\.(amocrm\.ru|kommo\.com))", referer)
        if domain_match:
            base_domain = domain_match.group(1)
    
    if not base_domain:
        return HTMLResponse("""
        <html>
        <head><title>Error</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>❌ Ошибка</h1>
            <p>Не удалось определить домен AmoCRM.</p>
            <p>Пожалуйста, введите домен (например, company.amocrm.ru) в настройках тенанта и попробуйте снова.</p>
        </body>
        </html>
        """, status_code=400)
    
    print(f"[INFO] AmoCRM callback: exchanging code for tokens, domain={base_domain}")
    
    # Обменять code на токены
    result = await amocrm_service.exchange_code_for_tokens(db, tenant_id, base_domain, code)
    if not result:
        return HTMLResponse("""
        <html>
        <head><title>Error</title></head>
        <body style="font-family: sans-serif; text-align: center; padding: 50px;">
            <h1>❌ Ошибка обмена кода</h1>
            <p>Не удалось получить токены от AmoCRM.</p>
            <p>Возможно, код авторизации истёк. Попробуйте подключить AmoCRM заново.</p>
        </body>
        </html>
        """, status_code=400)
    
    print(f"[INFO] AmoCRM callback: tokens saved for tenant {tenant_id}")
    
    # Redirect на frontend если FRONTEND_URL задан
    frontend_url = os.getenv("FRONTEND_URL", "").strip()
    if frontend_url:
        redirect_url = f"{frontend_url.rstrip('/')}/admin/tenants?amocrm=connected&tenant_id={tenant_id}"
        return RedirectResponse(url=redirect_url)
    
    # Fallback: показать HTML страницу успеха
    return HTMLResponse(f"""
    <html>
    <head><title>amoCRM Connected</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>✅ amoCRM подключена</h1>
        <p>Интеграция с amoCRM успешно настроена для tenant #{tenant_id}.</p>
        <p>Вы можете закрыть это окно и вернуться в админ-панель.</p>
        <script>
            if (window.opener) {{
                window.opener.postMessage({{ type: 'amocrm_connected', tenant_id: {tenant_id} }}, '*');
            }}
            setTimeout(function() {{ window.close(); }}, 3000);
        </script>
    </body>
    </html>
    """)
