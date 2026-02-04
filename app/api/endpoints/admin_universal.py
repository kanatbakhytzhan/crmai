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


async def _require_tenant_access(db: AsyncSession, tenant_id: int, current_user: User) -> str:
    """Проверка доступа: admin или owner/rop в tenant. Возвращает роль."""
    if getattr(current_user, "is_admin", False):
        return "admin"
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    if role in ("owner", "rop"):
        return role
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")


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
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return _safe_json_error(e.detail, e.status_code)
    except Exception as e:
        print(f"[ERROR] get_tenant_settings access check failed: {e}")
        return _safe_json_error("Access check failed", 403)
    
    try:
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if not tenant:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "detail": f"Tenant {tenant_id} not found"}
            )
        
        print(f"[INFO] get_tenant_settings: tenant_id={tenant_id}, name={tenant.name}")
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
        await _require_tenant_access(db, tenant_id, current_user)
    except HTTPException as e:
        return _safe_json_error(e.detail, e.status_code)
    except Exception as e:
        return _safe_json_error("Access check failed", 403)
    
    try:
        tenant = await crud.update_tenant(
            db,
            tenant_id,
            whatsapp_source=body.whatsapp_source,
            ai_enabled_global=body.ai_enabled_global,
            ai_prompt=body.ai_prompt,
            ai_after_lead_submitted_behavior=body.ai_after_lead_submitted_behavior,
            amocrm_base_domain=body.amocrm_base_domain,
        )
        if not tenant:
            return JSONResponse(status_code=404, content={"ok": False, "detail": "Tenant not found"})
        
        print(f"[INFO] update_tenant_settings: tenant_id={tenant_id}, updated fields={body.model_dump(exclude_unset=True)}")
        response = await _build_tenant_settings_response(db, tenant_id, tenant)
        return response
        
    except Exception as e:
        print(f"[ERROR] update_tenant_settings failed for tenant {tenant_id}: {type(e).__name__}: {e}")
        traceback.print_exc()
        return _safe_json_error(f"Failed to update settings: {type(e).__name__}")


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
    
    # Check ENV variables first
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
    
    # Determine base_domain: from query or from tenant settings
    domain = (base_domain or "").strip().lower()
    if not domain:
        try:
            tenant = await crud.get_tenant_by_id(db, tenant_id)
            if tenant:
                domain = (getattr(tenant, "amocrm_base_domain", None) or "").strip().lower()
        except Exception as e:
            print(f"[WARN] Failed to get tenant for domain: {e}")
    
    # Normalize domain - strip protocol and trailing slash
    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]
    domain = domain.rstrip("/").lower()
    
    if not domain:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "detail": "base_domain is required. Example: baxa.amocrm.ru",
                "code": "BASE_DOMAIN_REQUIRED"
            }
        )
    
    # Validate domain format
    if not re.match(r"^[\w\-]+\.(amocrm\.ru|kommo\.com)$", domain, re.IGNORECASE):
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "detail": f"Invalid base_domain format: '{domain}'. Must be like 'company.amocrm.ru' or 'company.kommo.com'",
                "code": "INVALID_DOMAIN_FORMAT"
            }
        )
    
    # Build auth URL
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
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # WhatsApp accounts
    wa_accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
    wa_binding = bool(wa_accounts)
    wa_active = any(a.is_active for a in wa_accounts)
    
    # AmoCRM
    amo_integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
    amo_connected = bool(amo_integration and amo_integration.is_active and amo_integration.access_token)
    
    # Mappings count
    pipeline_mappings = await crud.list_pipeline_mappings(db, tenant_id, "amocrm")
    field_mappings = await crud.list_field_mappings(db, tenant_id, "amocrm")
    
    return {
        "ok": True,
        "tenant_id": tenant_id,
        "tenant_name": tenant.name,
        "settings": {
            "whatsapp_source": getattr(tenant, "whatsapp_source", "chatflow"),
            "ai_enabled_global": getattr(tenant, "ai_enabled_global", True),
            "ai_enabled": getattr(tenant, "ai_enabled", True),
            "ai_prompt_len": len(tenant.ai_prompt or ""),
            "ai_after_lead_submitted_behavior": getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close"),
        },
        "whatsapp": {
            "binding_exists": wa_binding,
            "is_active": wa_active,
            "accounts_count": len(wa_accounts),
        },
        "amocrm": {
            "connected": amo_connected,
            "is_active": amo_integration.is_active if amo_integration else False,
            "base_domain": amo_integration.base_domain if amo_integration else None,
            "token_expires_at": amo_integration.token_expires_at.isoformat() if amo_integration and amo_integration.token_expires_at else None,
        },
        "mappings": {
            "pipeline_count": len(pipeline_mappings),
            "field_count": len(field_mappings),
        },
    }


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
    await _require_tenant_access(db, tenant_id, current_user)
    
    checks = []
    overall_ok = True
    
    # 1) Check tenant exists
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
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
    code: str,
    state: str,
    referer: str = "",
    db: AsyncSession = Depends(get_db),
):
    """
    Публичный callback для AmoCRM OAuth. amoCRM редиректит сюда с code и state=tenant_{id}.
    Извлекаем tenant_id из state, определяем base_domain из referer.
    """
    import re
    from fastapi.responses import HTMLResponse
    
    # Извлекаем tenant_id из state
    match = re.match(r"tenant_(\d+)", state or "")
    if not match:
        return HTMLResponse("<h1>Error</h1><p>Invalid state parameter</p>", status_code=400)
    tenant_id = int(match.group(1))
    
    # Определяем base_domain из referer (пример: https://example.amocrm.ru/...)
    base_domain = None
    if referer:
        domain_match = re.search(r"https?://([^/]+\.amocrm\.\w+)", referer)
        if domain_match:
            base_domain = domain_match.group(1)
    
    if not base_domain:
        # Fallback: попробовать получить из существующей интеграции
        integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
        if integration and integration.base_domain:
            base_domain = integration.base_domain
    
    if not base_domain:
        return HTMLResponse("<h1>Error</h1><p>Could not determine amoCRM domain. Please try again from admin panel.</p>", status_code=400)
    
    result = await amocrm_service.exchange_code_for_tokens(db, tenant_id, base_domain, code)
    if not result:
        return HTMLResponse("<h1>Error</h1><p>Failed to exchange authorization code. Please try again.</p>", status_code=400)
    
    return HTMLResponse(f"""
    <html>
    <head><title>amoCRM Connected</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>✅ amoCRM подключена</h1>
        <p>Интеграция с amoCRM успешно настроена для tenant #{tenant_id}.</p>
        <p>Вы можете закрыть это окно.</p>
        <script>
            if (window.opener) {{
                window.opener.postMessage({{ type: 'amocrm_connected', tenant_id: {tenant_id} }}, '*');
            }}
            setTimeout(function() {{ window.close(); }}, 3000);
        </script>
    </body>
    </html>
    """)
