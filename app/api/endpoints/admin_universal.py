"""
Universal Admin Console API endpoints.
Tenant settings, AmoCRM connect, pipeline/field mappings, mute from lead, diagnostics.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user, get_current_admin_or_owner_or_rop
from app.database import crud
from app.database.models import User
from app.schemas.tenant import (
    TenantSettingsResponse,
    TenantSettingsUpdate,
    ChatFlowBindingSnapshot,
    AmoCRMSnapshot,
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


async def _require_tenant_access(db: AsyncSession, tenant_id: int, current_user: User) -> str:
    """Проверка доступа: admin или owner/rop в tenant. Возвращает роль."""
    if getattr(current_user, "is_admin", False):
        return "admin"
    role = await crud.get_tenant_user_role(db, tenant_id, current_user.id)
    if role in ("owner", "rop"):
        return role
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin or tenant owner/rop required")


# ========== Tenant Settings ==========

@router.get("/tenants/{tenant_id}/settings", response_model=TenantSettingsResponse, summary="Настройки tenant для Universal Admin")
async def get_tenant_settings(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Получить настройки tenant со снапшотами WhatsApp и AmoCRM.
    Включает: whatsapp_source, ai_enabled_global, ai_prompt, ai_after_lead_submitted_behavior, amocrm_base_domain.
    Плюс: whatsapp (ChatFlow binding snapshot), amocrm (integration status snapshot).
    """
    await _require_tenant_access(db, tenant_id, current_user)
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        return {"ok": False, "detail": "Tenant not found"}
    
    # Get ChatFlow binding snapshot
    whatsapp_snapshot_dict = await crud.get_chatflow_binding_snapshot(db, tenant_id)
    whatsapp_snapshot = ChatFlowBindingSnapshot(**whatsapp_snapshot_dict)
    
    # Get AmoCRM integration snapshot
    integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
    if integration:
        amocrm_snapshot = AmoCRMSnapshot(
            connected=bool(integration.access_token),
            is_active=integration.is_active,
            base_domain=integration.base_domain,
            token_expires_at=integration.token_expires_at,
        )
    else:
        amocrm_snapshot = AmoCRMSnapshot()
    
    return TenantSettingsResponse(
        whatsapp_source=getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
        ai_enabled_global=getattr(tenant, "ai_enabled_global", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
        ai_after_lead_submitted_behavior=getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
        amocrm_base_domain=getattr(tenant, "amocrm_base_domain", None),
        whatsapp=whatsapp_snapshot,
        amocrm=amocrm_snapshot,
    )


@router.patch("/tenants/{tenant_id}/settings", response_model=TenantSettingsResponse, summary="Обновить настройки tenant")
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
    await _require_tenant_access(db, tenant_id, current_user)
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
        return {"ok": False, "detail": "Tenant not found"}
    
    # Get ChatFlow binding snapshot
    whatsapp_snapshot_dict = await crud.get_chatflow_binding_snapshot(db, tenant_id)
    whatsapp_snapshot = ChatFlowBindingSnapshot(**whatsapp_snapshot_dict)
    
    # Get AmoCRM integration snapshot
    integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
    if integration:
        amocrm_snapshot = AmoCRMSnapshot(
            connected=bool(integration.access_token),
            is_active=integration.is_active,
            base_domain=integration.base_domain,
            token_expires_at=integration.token_expires_at,
        )
    else:
        amocrm_snapshot = AmoCRMSnapshot()
    
    return TenantSettingsResponse(
        whatsapp_source=getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
        ai_enabled_global=getattr(tenant, "ai_enabled_global", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
        ai_after_lead_submitted_behavior=getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
        amocrm_base_domain=getattr(tenant, "amocrm_base_domain", None),
        whatsapp=whatsapp_snapshot,
        amocrm=amocrm_snapshot,
    )


# ========== AmoCRM Integration ==========

@router.get("/tenants/{tenant_id}/amocrm/auth-url", response_model=AmoCRMAuthUrlResponse, summary="URL для OAuth в amoCRM")
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
    """
    await _require_tenant_access(db, tenant_id, current_user)
    
    # Determine base_domain: from query or from tenant settings
    domain = (base_domain or "").strip()
    if not domain:
        tenant = await crud.get_tenant_by_id(db, tenant_id)
        if tenant:
            domain = getattr(tenant, "amocrm_base_domain", None) or ""
    
    # Normalize domain
    domain = domain.strip()
    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]
    domain = domain.rstrip("/")
    
    if not domain:
        return AmoCRMAuthUrlResponse(
            ok=False,
            detail="base_domain is required. Provide ?base_domain=xxx.amocrm.ru or save it in tenant settings first."
        )
    
    # Validate domain format
    import re
    if not re.match(r"^[\w\-]+\.(amocrm\.ru|kommo\.com)$", domain, re.IGNORECASE):
        return AmoCRMAuthUrlResponse(
            ok=False,
            detail=f"Invalid base_domain format: '{domain}'. Must be like 'company.amocrm.ru' or 'company.kommo.com'"
        )
    
    # Build auth URL
    url = amocrm_service.build_auth_url(tenant_id, domain)
    if not url:
        return AmoCRMAuthUrlResponse(
            ok=False,
            detail="AMO_CLIENT_ID or AMO_REDIRECT_URL not configured on server. Contact administrator."
        )
    
    # Save domain to tenant settings for future use
    await crud.update_tenant(db, tenant_id, amocrm_base_domain=domain)
    
    return AmoCRMAuthUrlResponse(ok=True, auth_url=url, base_domain=domain)


@router.post("/tenants/{tenant_id}/amocrm/callback", summary="Обмен code на токены amoCRM")
async def amocrm_callback(
    tenant_id: int,
    body: AmoCRMCallbackBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обменять code на access_token/refresh_token и сохранить."""
    await _require_tenant_access(db, tenant_id, current_user)
    result = await amocrm_service.exchange_code_for_tokens(db, tenant_id, body.base_domain, body.code)
    if not result:
        return {"ok": False, "detail": "Failed to exchange code for tokens. Check server logs."}
    # Also save base_domain to tenant settings
    await crud.update_tenant(db, tenant_id, amocrm_base_domain=body.base_domain)
    return {"ok": True, **result}


@router.get("/tenants/{tenant_id}/amocrm/status", response_model=AmoCRMStatusResponse, summary="Статус интеграции amoCRM")
async def get_amocrm_status(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Статус интеграции amoCRM (без токенов)."""
    await _require_tenant_access(db, tenant_id, current_user)
    integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
    if not integration:
        return AmoCRMStatusResponse(is_active=False, connected=False)
    return AmoCRMStatusResponse(
        is_active=integration.is_active,
        base_domain=integration.base_domain,
        token_expires_at=integration.token_expires_at,
        connected=bool(integration.access_token),
    )


@router.post("/tenants/{tenant_id}/amocrm/refresh", summary="Принудительно обновить токены amoCRM")
async def refresh_amocrm_tokens(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Принудительно обновить токены amoCRM."""
    await _require_tenant_access(db, tenant_id, current_user)
    client = await amocrm_service.get_amocrm_client(db, tenant_id)
    if not client:
        return {"ok": False, "detail": "AmoCRM integration not active or not connected"}
    refreshed = await client._refresh_if_needed()
    return {"ok": True, "refreshed": refreshed}


@router.post("/tenants/{tenant_id}/amocrm/disconnect", summary="Отключить интеграцию amoCRM")
async def disconnect_amocrm(
    tenant_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Деактивировать интеграцию amoCRM."""
    await _require_tenant_access(db, tenant_id, current_user)
    result = await crud.deactivate_tenant_integration(db, tenant_id, "amocrm")
    return {"ok": result}


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
