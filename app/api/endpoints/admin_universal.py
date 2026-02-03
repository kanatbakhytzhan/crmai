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
    """Получить настройки tenant: whatsapp_source, ai_enabled_global, ai_prompt, ai_after_lead_submitted_behavior."""
    await _require_tenant_access(db, tenant_id, current_user)
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantSettingsResponse(
        whatsapp_source=getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
        ai_enabled_global=getattr(tenant, "ai_enabled_global", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
        ai_after_lead_submitted_behavior=getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
    )


@router.patch("/tenants/{tenant_id}/settings", response_model=TenantSettingsResponse, summary="Обновить настройки tenant")
async def update_tenant_settings(
    tenant_id: int,
    body: TenantSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Обновить настройки tenant."""
    await _require_tenant_access(db, tenant_id, current_user)
    tenant = await crud.update_tenant(
        db,
        tenant_id,
        whatsapp_source=body.whatsapp_source,
        ai_enabled_global=body.ai_enabled_global,
        ai_prompt=body.ai_prompt,
        ai_after_lead_submitted_behavior=body.ai_after_lead_submitted_behavior,
    )
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantSettingsResponse(
        whatsapp_source=getattr(tenant, "whatsapp_source", "chatflow") or "chatflow",
        ai_enabled_global=getattr(tenant, "ai_enabled_global", True),
        ai_prompt=getattr(tenant, "ai_prompt", None),
        ai_after_lead_submitted_behavior=getattr(tenant, "ai_after_lead_submitted_behavior", "polite_close") or "polite_close",
    )


# ========== AmoCRM Integration ==========

@router.get("/tenants/{tenant_id}/amocrm/auth-url", response_model=AmoCRMAuthUrlResponse, summary="URL для OAuth в amoCRM")
async def get_amocrm_auth_url(
    tenant_id: int,
    base_domain: str = Query(..., description="Домен amoCRM, например example.amocrm.ru"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Сформировать URL для OAuth авторизации в amoCRM."""
    await _require_tenant_access(db, tenant_id, current_user)
    url = amocrm_service.build_auth_url(tenant_id, base_domain)
    if not url:
        return AmoCRMAuthUrlResponse(error="AMO_CLIENT_ID or AMO_REDIRECT_URL not configured")
    return AmoCRMAuthUrlResponse(url=url)


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
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")
    return result


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
        raise HTTPException(status_code=400, detail="AmoCRM integration not active")
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
