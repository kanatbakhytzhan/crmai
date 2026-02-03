"""
AmoCRM интеграция: OAuth, API методы, авто-refresh токенов.
Токены НЕ логируются. Маскировка при выводе.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

log = logging.getLogger(__name__)

AMOCRM_TOKEN_URL = "https://{domain}/oauth2/access_token"
AMOCRM_API_BASE = "https://{domain}/api/v4"


def _mask_token(token: str | None) -> str:
    """Маскировать токен для логов (первые 4 символа)."""
    if not token:
        return "(none)"
    return token[:4] + "***" if len(token) > 4 else "***"


class AmoCRMClient:
    """Клиент для AmoCRM API с авто-refresh."""

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        base_domain: str,
        access_token: str,
        refresh_token: str,
        token_expires_at: datetime | None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.base_domain = base_domain
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_expires_at = token_expires_at

    async def _refresh_if_needed(self) -> bool:
        """Обновить токен если истёк (или почти истёк). Возвращает True если обновлён."""
        if self._token_expires_at and self._token_expires_at > datetime.utcnow() + timedelta(minutes=5):
            return False
        settings = get_settings()
        if not settings.amo_client_id or not settings.amo_client_secret:
            log.warning("[AMOCRM] refresh skipped: no client_id/secret in env")
            return False
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    AMOCRM_TOKEN_URL.format(domain=self.base_domain),
                    json={
                        "client_id": settings.amo_client_id,
                        "client_secret": settings.amo_client_secret,
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                        "redirect_uri": settings.amo_redirect_url or "",
                    },
                )
                if resp.status_code != 200:
                    log.error("[AMOCRM] refresh failed: %s %s", resp.status_code, resp.text[:200])
                    return False
                data = resp.json()
                self._access_token = data.get("access_token", "")
                self._refresh_token = data.get("refresh_token", self._refresh_token)
                expires_in = data.get("expires_in", 86400)
                self._token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                # Сохранить в БД
                from app.database import crud
                await crud.update_tenant_integration_tokens(
                    self.db,
                    tenant_id=self.tenant_id,
                    provider="amocrm",
                    access_token=self._access_token,
                    refresh_token=self._refresh_token,
                    token_expires_at=self._token_expires_at,
                )
                log.info("[AMOCRM] token refreshed tenant_id=%s expires=%s", self.tenant_id, self._token_expires_at)
                return True
        except Exception as e:
            log.error("[AMOCRM] refresh error: %s", type(e).__name__)
            return False

    async def _request(self, method: str, path: str, **kwargs) -> dict | list | None:
        """Запрос к API с авто-refresh при 401."""
        await self._refresh_if_needed()
        url = AMOCRM_API_BASE.format(domain=self.base_domain) + path
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.request(method, url, headers=headers, **kwargs)
                if resp.status_code == 401:
                    log.warning("[AMOCRM] 401, trying refresh")
                    refreshed = await self._refresh_if_needed()
                    if refreshed:
                        headers["Authorization"] = f"Bearer {self._access_token}"
                        resp = await client.request(method, url, headers=headers, **kwargs)
                if resp.status_code >= 400:
                    log.error("[AMOCRM] API error: %s %s %s", method, path, resp.status_code)
                    return None
                return resp.json() if resp.text else {}
        except Exception as e:
            log.error("[AMOCRM] request error: %s %s %s", method, path, type(e).__name__)
            return None

    async def find_contact_by_phone(self, phone: str) -> dict | None:
        """Найти контакт по телефону."""
        data = await self._request("GET", "/contacts", params={"query": phone})
        if not data or not isinstance(data, dict):
            return None
        embedded = data.get("_embedded", {})
        contacts = embedded.get("contacts", [])
        return contacts[0] if contacts else None

    async def create_contact(self, name: str, phone: str) -> dict | None:
        """Создать контакт."""
        body = [{"name": name, "custom_fields_values": [{"field_code": "PHONE", "values": [{"value": phone}]}]}]
        data = await self._request("POST", "/contacts", json=body)
        if not data or not isinstance(data, dict):
            return None
        embedded = data.get("_embedded", {})
        contacts = embedded.get("contacts", [])
        return contacts[0] if contacts else None

    async def find_open_lead_for_contact(self, contact_id: int, pipeline_id: str | None = None) -> dict | None:
        """Найти открытую (не закрытую) сделку для контакта."""
        params = {"filter[contacts][id]": contact_id}
        if pipeline_id:
            params["filter[pipeline_id]"] = pipeline_id
        data = await self._request("GET", "/leads", params=params)
        if not data or not isinstance(data, dict):
            return None
        embedded = data.get("_embedded", {})
        leads = embedded.get("leads", [])
        for lead in leads:
            if not lead.get("closed_at"):
                return lead
        return None

    async def create_lead_in_stage(self, contact_id: int, status_id: int, name: str = "Заявка с сайта", pipeline_id: int | None = None) -> dict | None:
        """Создать сделку в указанной стадии."""
        body = [{"name": name, "status_id": status_id, "_embedded": {"contacts": [{"id": contact_id}]}}]
        if pipeline_id:
            body[0]["pipeline_id"] = pipeline_id
        data = await self._request("POST", "/leads", json=body)
        if not data or not isinstance(data, dict):
            return None
        embedded = data.get("_embedded", {})
        leads = embedded.get("leads", [])
        return leads[0] if leads else None

    async def add_note_to_lead(self, lead_id: int, text: str) -> dict | None:
        """Добавить примечание к сделке."""
        body = [{"entity_id": lead_id, "note_type": "common", "params": {"text": text}}]
        data = await self._request("POST", f"/leads/{lead_id}/notes", json=body)
        if not data or not isinstance(data, dict):
            return None
        embedded = data.get("_embedded", {})
        notes = embedded.get("notes", [])
        return notes[0] if notes else None

    async def update_lead_fields(self, lead_id: int, fields: dict) -> dict | None:
        """Обновить кастомные поля сделки. fields: {field_id: value}."""
        if not fields:
            return None
        custom_fields = [{"field_id": int(k), "values": [{"value": v}]} for k, v in fields.items() if v is not None]
        if not custom_fields:
            return None
        body = {"custom_fields_values": custom_fields}
        data = await self._request("PATCH", f"/leads/{lead_id}", json=body)
        return data

    async def move_lead_stage(self, lead_id: int, status_id: int, pipeline_id: int | None = None) -> dict | None:
        """Переместить сделку в другую стадию."""
        body: dict[str, Any] = {"status_id": status_id}
        if pipeline_id:
            body["pipeline_id"] = pipeline_id
        data = await self._request("PATCH", f"/leads/{lead_id}", json=body)
        return data


async def get_amocrm_client(db: AsyncSession, tenant_id: int) -> AmoCRMClient | None:
    """Создать клиент AmoCRM если интеграция активна."""
    from app.database import crud
    integration = await crud.get_tenant_integration(db, tenant_id, "amocrm")
    if not integration or not integration.is_active:
        return None
    if not integration.access_token or not integration.base_domain:
        return None
    return AmoCRMClient(
        db=db,
        tenant_id=tenant_id,
        base_domain=integration.base_domain,
        access_token=integration.access_token,
        refresh_token=integration.refresh_token or "",
        token_expires_at=integration.token_expires_at,
    )


def build_auth_url(tenant_id: int, base_domain: str) -> str | None:
    """Сформировать URL для OAuth авторизации в amoCRM."""
    settings = get_settings()
    if not settings.amo_client_id or not settings.amo_redirect_url:
        return None
    state = f"tenant_{tenant_id}"
    return (
        f"https://{base_domain}/oauth"
        f"?client_id={settings.amo_client_id}"
        f"&mode=post_message"
        f"&redirect_uri={settings.amo_redirect_url}"
        f"&state={state}"
    )


async def exchange_code_for_tokens(
    db: AsyncSession,
    tenant_id: int,
    base_domain: str,
    code: str,
) -> dict | None:
    """Обменять code на access_token/refresh_token и сохранить."""
    settings = get_settings()
    if not settings.amo_client_id or not settings.amo_client_secret:
        log.error("[AMOCRM] exchange: no client_id/secret")
        return None
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                AMOCRM_TOKEN_URL.format(domain=base_domain),
                json={
                    "client_id": settings.amo_client_id,
                    "client_secret": settings.amo_client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.amo_redirect_url or "",
                },
            )
            if resp.status_code != 200:
                log.error("[AMOCRM] exchange failed: %s %s", resp.status_code, resp.text[:200])
                return None
            data = resp.json()
            access_token = data.get("access_token", "")
            refresh_token = data.get("refresh_token", "")
            expires_in = data.get("expires_in", 86400)
            token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            from app.database import crud
            await crud.upsert_tenant_integration(
                db,
                tenant_id=tenant_id,
                provider="amocrm",
                base_domain=base_domain,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                is_active=True,
            )
            log.info("[AMOCRM] tokens saved tenant_id=%s domain=%s", tenant_id, base_domain)
            return {"ok": True, "expires_at": token_expires_at.isoformat()}
    except Exception as e:
        log.error("[AMOCRM] exchange error: %s", type(e).__name__)
        return None
