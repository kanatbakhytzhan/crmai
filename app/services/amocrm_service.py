
import aiohttp
import asyncio
import logging
import time
import re
from typing import Optional, Dict, List, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update
from sqlalchemy.sql import text

from app.database import models
from app.core.config import get_settings

log = logging.getLogger(__name__)

class AmoCRMService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    async def _get_integration(self, tenant_id: int) -> Optional[models.TenantIntegration]:
        result = await self.db.execute(
            select(models.TenantIntegration).where(
                models.TenantIntegration.tenant_id == tenant_id,
                models.TenantIntegration.provider == "amocrm",
                models.TenantIntegration.is_active == True
            )
        )
        return result.scalars().first()

    async def _refresh_access_token(self, integration: models.TenantIntegration) -> bool:
        """Обновить токен через refresh_token."""
        if not integration.refresh_token or not integration.base_domain:
            return False

        if not self.settings.amo_client_id or not self.settings.amo_client_secret:
            log.error("AmoCRM credentials not configured in settings")
            return False

        url = f"https://{integration.base_domain}/oauth2/access_token"
        payload = {
            "client_id": self.settings.amo_client_id,
            "client_secret": self.settings.amo_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": integration.refresh_token,
            "redirect_uri": self.settings.amo_redirect_url or "https://example.com"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        integration.access_token = data["access_token"]
                        integration.refresh_token = data["refresh_token"]
                        expires_in = data.get("expires_in", 86400)
                        # integration.expires_at = ... (if we had that column, currently just token)
                        await self.db.commit()
                        return True
                    else:
                        text = await resp.text()
                        log.error(f"AmoCRM Refresh Failed {resp.status}: {text}")
                        return False
        except Exception as e:
            log.error(f"AmoCRM Refresh Exception: {e}")
            return False

    async def _make_request(
        self, 
        integration: models.TenantIntegration, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None,
        params: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Выполнить запрос к API AmoCRM с авто-рефрешем токена."""
        if not integration.access_token:
            raise Exception("No access token")

        base_url = f"https://{integration.base_domain}"
        url = f"{base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {integration.access_token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data, params=params) as resp:
                if resp.status == 401:
                    log.warning(f"AmoCRM 401 for tenant {integration.tenant_id}. Refreshing token...")
                    if await self._refresh_access_token(integration):
                        # Retry once
                        headers["Authorization"] = f"Bearer {integration.access_token}"
                        async with session.request(method, url, headers=headers, json=data, params=params) as resp2:
                             if resp2.status >= 400:
                                 text_resp = await resp2.text()
                                 raise Exception(f"AmoCRM Error after refresh: {resp2.status} {text_resp}")
                             if resp2.status == 204: return {}
                             return await resp2.json()
                    else:
                        raise Exception("AmoCRM Token Expired and Refresh Failed")
                
                if resp.status >= 400:
                    text_resp = await resp.text()
                    log.error(f"AmoCRM error {resp.status} on {endpoint}: {text_resp}")
                    raise Exception(f"AmoCRM Error: {resp.status}")

                if resp.status == 204:
                    return {}
                return await resp.json()

    # --- Discovery API ---

    async def get_account_info(self, tenant_id: int) -> Dict:
        integ = await self._get_integration(tenant_id)
        if not integ:
            return {"connected": False}
        
        try:
            data = await self._make_request(integ, "GET", "/api/v4/account")
            return {"connected": True, "account": data}
        except Exception as e:
            return {"connected": True, "error": str(e)}

    async def list_pipelines(self, tenant_id: int) -> List[Dict]:
        integ = await self._get_integration(tenant_id)
        if not integ: return []
        try:
            data = await self._make_request(integ, "GET", "/api/v4/leads/pipelines")
            return data.get("_embedded", {}).get("pipelines", [])
        except Exception:
            return []

    async def list_custom_fields(self, tenant_id: int, entity: str = "leads") -> List[Dict]:
        integ = await self._get_integration(tenant_id)
        if not integ: return []
        try:
            data = await self._make_request(integ, "GET", f"/api/v4/{entity}/custom_fields")
            return data.get("_embedded", {}).get("custom_fields", [])
        except Exception:
            return []

    # --- Sync Logic ---

    async def sync_to_amocrm(
        self, 
        tenant: models.Tenant, 
        message_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Основной метод синхронизации.
        1. Ищет/создает контакт по телефону.
        2. Ищет открытую сделку или создает новую.
        3. Добавляет примечание (сообщение).
        4. Применяет правила смены этапа.
        """
        integ = await self._get_integration(tenant.id)
        if not integ:
            return {"ok": False, "reason": "No AmoCRM integration"}

        phone = message_data.get("phone_number")
        text_body = message_data.get("body", "")
        sender_name = message_data.get("sender_name", "Unknown")

        if not phone:
            return {"ok": False, "reason": "No phone number"}
        
        # 1. Find Contact (using last 10 digits to be safe)
        contact_id = await self._find_contact_by_phone(integ, phone)
        if not contact_id:
            contact_id = await self._create_contact(integ, name=sender_name or phone, phone=phone)
            log.info(f"Created AmoCRM contact {contact_id} for {phone}")
        else:
            log.info(f"Found AmoCRM contact {contact_id} for {phone}")

        # 2. Find Active Lead (Deal)
        active_lead_id = await self._find_active_lead(integ, contact_id)
        
        if not active_lead_id:
            # Create new lead
            pipeline_id = getattr(tenant, "default_pipeline_id", None)
            
            # Map "new_lead" stage to status_id
            status_id = await self._get_mapped_status(tenant.id, "new_lead")
            
            active_lead_id = await self._create_lead(
                integ, 
                contact_id, 
                title=f"WhatsApp: {sender_name}", 
                pipeline_id=int(pipeline_id) if pipeline_id else None,
                status_id=int(status_id) if status_id else None
            )
            log.info(f"Created new AmoCRM lead {active_lead_id}")

        # 3. Add Message Note
        await self._add_note(integ, entity_type="leads", entity_id=active_lead_id, text=f"{sender_name}: {text_body}")
        
        # 4. Apply Rules (Stage Movement)
        await self._apply_rules(integ, tenant.id, active_lead_id, text_body)

        return {
            "ok": True,
            "contact_id": contact_id,
            "lead_id": active_lead_id
        }

    async def _find_contact_by_phone(self, integ, phone: str) -> Optional[int]:
        # AmoCRM contact search. normalize to last 10 digits
        clean_phone = re.sub(r"\D", "", phone)[-10:]
        if len(clean_phone) < 6: clean_phone = phone # fallback
        
        params = {"query": clean_phone}
        try:
            data = await self._make_request(integ, "GET", "/api/v4/contacts", params=params)
            contacts = data.get("_embedded", {}).get("contacts", [])
            if contacts:
                return contacts[0]["id"]
            return None
        except Exception:
            return None

    async def _create_contact(self, integ, name: str, phone: str) -> int:
        payload = [{
            "name": name,
            "custom_fields_values": [
                {
                    "field_code": "PHONE",
                    "values": [{"value": phone, "enum_code": "WORK"}]
                }
            ]
        }]
        res = await self._make_request(integ, "POST", "/api/v4/contacts", data=payload)
        return res["_embedded"]["contacts"][0]["id"]

    async def _find_active_lead(self, integ, contact_id: int) -> Optional[int]:
        try:
            links = await self._make_request(integ, "GET", f"/api/v4/contacts/{contact_id}/links")
            linked_leads = links.get("_embedded", {}).get("links", [])
            lead_ids = [l["to_entity_id"] for l in linked_leads if l["to_entity_type"] == "leads"]
            
            if not lead_ids: return None

            ids_str = "&".join([f"filter[id][]={lid}" for lid in lead_ids[:10]])
            if not ids_str: return None
            
            leads_data = await self._make_request(integ, "GET", f"/api/v4/leads?{ids_str}")
            leads = leads_data.get("_embedded", {}).get("leads", [])
            
            for lead in leads:
                # 142=Success, 143=Closed/Lost are default closed statuses in some setups, but 
                # actually AmoCRM pipeline statuses are custom. 
                # But usually 142/143 are system closed. 
                # Better approach: check pipeline details? 
                # For now assume if status_id is not 142 (Success) and not 143 (Lost).
                # Note: this is risky if user has different closed IDs. 
                # Ideally we should fetch pipeline and check "is_closed". 
                # But for now, let's just pick the most recent one? 
                # Or assume standard.
                sid = lead["status_id"]
                if sid != 142 and sid != 143:
                    return lead["id"]
            return None
        except Exception:
            return None

    async def _create_lead(self, integ, contact_id: int, title: str, pipeline_id: int, status_id: int) -> int:
        lead_data = {
            "name": title,
            "_embedded": {
                "contacts": [{"id": contact_id}]
            }
        }
        if pipeline_id:
            lead_data["pipeline_id"] = pipeline_id
        if status_id:
            lead_data["status_id"] = status_id
            
        res = await self._make_request(integ, "POST", "/api/v4/leads", data=[lead_data])
        return res["_embedded"]["leads"][0]["id"]

    async def _add_note(self, integ, entity_type: str, entity_id: int, text: str):
        payload = [{
            "entity_id": entity_id,
            "note_type": "common",
            "params": {"text": text}
        }]
        await self._make_request(integ, "POST", f"/api/v4/{entity_type}/{entity_id}/notes", data=payload)

    async def _get_mapped_status(self, tenant_id: int, stage_key: str) -> Optional[int]:
        # Check database for mapping
        q = select(models.TenantPipelineMapping.stage_id).where(
            models.TenantPipelineMapping.tenant_id == tenant_id,
            models.TenantPipelineMapping.stage_key == stage_key,
            models.TenantPipelineMapping.provider == "amocrm",
            models.TenantPipelineMapping.is_active == True
        )
        res = await self.db.execute(q)
        sid = res.scalar()
        return int(sid) if sid else None

    async def _update_lead_status(self, integ, lead_id: int, status_id: int):
        payload = [{"id": lead_id, "status_id": status_id}]
        await self._make_request(integ, "PATCH", "/api/v4/leads", data=payload)

    async def _apply_rules(self, integ, tenant_id: int, lead_id: int, text: str):
        """Простая логика распределения."""
        txt = text.lower()
        target_stage_key = None
        
        # 1. "отказ/не нужно" -> "lost"
        if any(w in txt for w in ["отказ", "не нужно", "не интересно"]):
            target_stage_key = "lost"

        # 2. "замер" + цифры (время/дата) -> "measurement_scheduled"
        # Simple heuristic: "замер" and some digit
        elif "замер" in txt and re.search(r"\d", txt):
            target_stage_key = "measurement_scheduled"
            
        # 3. "адрес" or "квадратура" -> "in_work"
        elif "адрес" in txt or "квадратура" in txt:
            target_stage_key = "in_work"
        
        if target_stage_key:
            status_id = await self._get_mapped_status(tenant_id, target_stage_key)
            if status_id:
                log.info(f"Moving lead {lead_id} to {target_stage_key} ({status_id}) based on rule")
                await self._update_lead_status(integ, lead_id, status_id)


