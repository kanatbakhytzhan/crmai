"""
Admin-only diagnostics: DB tables check, smoke-test, QA-панель.
Доступ: get_current_admin для большинства; get_current_admin_or_owner для UI и тестов.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.responses import HTMLResponse
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.api.deps import get_db, get_current_admin, get_current_admin_or_owner
from app.core.config import get_settings
from app.database import crud
from app.database.models import User, Lead, Tenant

router = APIRouter()

TABLES_TO_CHECK = [
    "tenants",
    "users",
    "leads",
    "lead_comments",
    "tenant_users",
    "conversations",
    "conversation_messages",
    "whatsapp_accounts",
]

TABLE_NOTES = {
    "lead_comments": "lead_comments missing: comments feature will fail",
    "tenant_users": "tenant_users missing: multi-user per tenant will fail",
    "conversations": "conversations missing: chat context will fail",
    "conversation_messages": "conversation_messages missing: chat context will fail",
    "whatsapp_accounts": "whatsapp_accounts missing: WhatsApp webhook will fail",
}


@router.get("/diagnostics/db")
async def diagnostics_db(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Автопроверка БД: существование таблиц.
    Возвращает tables (name -> true/false) и notes (предупреждения).
    Только для админов.
    """
    db_url = get_settings().database_url
    is_postgres = "postgresql" in db_url
    tables = {}
    notes = []

    for table_name in TABLES_TO_CHECK:
        try:
            if is_postgres:
                result = await db.execute(
                    text(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = :t"
                    ),
                    {"t": table_name},
                )
            else:
                result = await db.execute(
                    text(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :t"
                    ),
                    {"t": table_name},
                )
            exists = result.scalar_one_or_none() is not None
            tables[table_name] = exists
            if not exists and table_name in TABLE_NOTES:
                notes.append(TABLE_NOTES[table_name])
        except Exception as e:
            tables[table_name] = False
            notes.append(f"{table_name}: check failed ({type(e).__name__})")

    return {
        "ok": True,
        "tables": tables,
        "notes": notes,
    }


@router.get("/diagnostics/db/schema", summary="Check DB schema columns")
async def diagnostics_db_schema(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Проверить наличие критичных колонок в tenants.
    Помогает отловить "UndefinedColumnError".
    """
    required_tenants_columns = [
        "amocrm_base_domain",
        "whatsapp_source",
        "ai_enabled_global",
        "ai_after_lead_submitted_behavior",
        "ai_prompt",
        "webhook_key",
    ]
    
    report = {"tenants": {}}
    notes = []
    
    for col in required_tenants_columns:
        try:
            # Пытаемся выбрать конкретную колонку
            await db.execute(text(f"SELECT {col} FROM tenants LIMIT 1"))
            report["tenants"][col] = True
        except Exception as e:
            report["tenants"][col] = False
            notes.append(f"tenants.{col} MISSING: {e}")
            
    return {
        "ok": True,
        "schema_report": report,
        "notes": notes,
        "status": "CRITICAL" if notes else "OK"
    }


@router.get("/diagnostics/leads-health", response_model=dict)
async def diagnostics_leads_health(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    CRM v2.5: доля лидов без tenant_id. total_leads, leads_without_tenant_id, sample.
    """
    r_total = await db.execute(select(func.count(Lead.id)))
    total_leads = r_total.scalar() or 0
    r_without = await db.execute(select(func.count(Lead.id)).where(Lead.tenant_id.is_(None)))
    leads_without_tenant_id = r_without.scalar() or 0
    r_sample = await db.execute(
        select(Lead).where(Lead.tenant_id.is_(None)).order_by(Lead.id.desc()).limit(20)
    )
    sample_leads = list(r_sample.scalars().all())
    sample = [
        {"id": l.id, "phone": getattr(l, "phone", None), "created_at": getattr(l, "created_at", None)}
        for l in sample_leads
    ]
    return {
        "ok": True,
        "total_leads": total_leads,
        "leads_without_tenant_id": leads_without_tenant_id,
        "leads_without_tenant_id_sample": sample,
    }


@router.post("/diagnostics/smoke-test")
async def diagnostics_smoke_test(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Smoke-test: (1) комментарий к последнему лиду; (2) whatsapp binding для первого tenant.
    Возвращает ok: true если всё прошло, иначе ok: false и reason.
    Только для админов.
    """
    # --- 1) Комментарий к лиду ---
    result = await db.execute(select(Lead).order_by(Lead.id.desc()).limit(1))
    lead = result.scalar_one_or_none()
    if not lead:
        return {"ok": False, "reason": "no_leads"}

    comment_id = None
    try:
        comment = await crud.create_lead_comment(
            db,
            lead_id=lead.id,
            user_id=current_user.id,
            text="[smoke-test] diagnostic check",
        )
        comment_id = comment.id
        comments = await crud.get_lead_comments(db, lead_id=lead.id, limit=10)
        if not any(c.id == comment_id for c in comments):
            await crud.delete_lead_comment(db, comment_id)
            return {"ok": False, "reason": "comment_created_but_not_found_in_list"}
        await crud.delete_lead_comment(db, comment_id)
    except Exception as e:
        if comment_id:
            try:
                await crud.delete_lead_comment(db, comment_id)
            except Exception:
                pass
        return {
            "ok": False,
            "reason": f"comment: {type(e).__name__}: {str(e)[:200]}",
            "created_test_comment_id": comment_id,
        }

    # --- 2) WhatsApp binding: upsert для первого tenant, затем list ---
    tenants = await crud.list_tenants(db)
    if not tenants:
        return {"ok": True}
    tenant_id = tenants[0].id
    try:
        acc = await crud.upsert_whatsapp_for_tenant(
            db,
            tenant_id=tenant_id,
            phone_number="+smoke-test",
            chatflow_token="smoke_token",
            chatflow_instance_id="smoke_instance",
            is_active=False,
        )
        accounts = await crud.list_whatsapp_accounts_by_tenant(db, tenant_id)
        if not accounts:
            return {"ok": False, "reason": "whatsapp_upsert_ok_but_list_empty"}
        if accounts[0].id != acc.id:
            return {"ok": False, "reason": "whatsapp_list_first_id_mismatch"}
    except Exception as e:
        return {
            "ok": False,
            "reason": f"whatsapp: {type(e).__name__}: {str(e)[:200]}",
        }

    # --- 3) Tenant по webhook_key (для ChatFlow webhook?key=...) ---
    t = tenants[0]
    webhook_key = getattr(t, "webhook_key", None) or ""
    if webhook_key:
        by_key = await crud.get_tenant_by_webhook_key(db, webhook_key)
        if not by_key or by_key.id != t.id:
            return {"ok": False, "reason": "tenant_by_webhook_key_mismatch"}
    return {"ok": True}


@router.post("/diagnostics/fix-leads-tenant", response_model=dict)
async def diagnostics_fix_leads_tenant(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Бэкофис: найти лиды с tenant_id IS NULL и попытаться проставить tenant_id.
    Правила: (a) conversation по remote_jid (lead.bot_user.user_id);
             (b) tenant где default_owner_user_id == lead.owner_id.
    Идемпотентно. Только для админов (JWT admin).
    Возвращает: { ok, fixed, skipped, skipped_ids, notes }.
    """
    result = await db.execute(select(Lead).where(Lead.tenant_id.is_(None)))
    leads_without_tenant = list(result.scalars().all())
    fixed = 0
    skipped_ids: list[int] = []
    notes: list[str] = []

    for lead in leads_without_tenant:
        resolved = await crud.resolve_lead_tenant_id(db, lead)
        if resolved is not None:
            lead.tenant_id = resolved
            await db.commit()
            await db.refresh(lead)
            fixed += 1
            notes.append(f"lead_id={lead.id} -> tenant_id={resolved}")
        else:
            skipped_ids.append(lead.id)
            bot_user = await crud.get_bot_user_by_id(db, lead.bot_user_id)
            remote_jid = (bot_user.user_id if bot_user else "") or ""
            notes.append(f"lead_id={lead.id} skipped (no conversation/tenant), remote_jid={remote_jid!r}")

    return {
        "ok": True,
        "fixed": fixed,
        "skipped": len(skipped_ids),
        "skipped_ids": skipped_ids,
        "notes": notes,
    }


@router.post("/diagnostics/backfill-lead-numbers", response_model=dict)
async def diagnostics_backfill_lead_numbers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin),
):
    """
    Проставить lead_number всем лидам, где lead_number IS NULL.
    Группировка по tenant_id (или owner_id при отсутствии tenant).
    Нумерация по created_at ASC. Возвращает { ok: true, updated: N }.
    Только для админов.
    """
    updated = await crud.backfill_lead_numbers(db)
    return {"ok": True, "updated": updated}


# ---------- QA Panel (admin/owner) ----------

QA_UI_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>BuildCRM QA / Diagnostics</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 24px auto; padding: 0 16px; }
    h1 { font-size: 1.25rem; }
    input[type="text"], input[type="number"] { width: 100%; max-width: 320px; padding: 6px 8px; margin: 4px 0; }
    button { padding: 8px 14px; margin: 4px 6px 4px 0; cursor: pointer; background: #2563eb; color: #fff; border: none; border-radius: 6px; }
    button:hover { background: #1d4ed8; }
    button.secondary { background: #64748b; }
    #result { background: #f1f5f9; padding: 12px; border-radius: 8px; white-space: pre-wrap; word-break: break-all; font-size: 12px; max-height: 60vh; overflow: auto; }
    .row { margin: 10px 0; }
    label { display: block; font-weight: 600; margin-bottom: 4px; }
  </style>
</head>
<body>
  <h1>BuildCRM — QA / Diagnostics</h1>
  <p>Проверка API без Postman. Сначала сохраните JWT (получить: <b>POST /api/auth/login</b>).</p>
  <div class="row">
    <label>JWT (Bearer)</label>
    <input type="text" id="token" placeholder="Вставьте access_token">
    <button onclick="saveToken()">Save token</button>
  </div>
  <div class="row">
    <button onclick="call('GET','/api/admin/diagnostics/db')">DB Tables Check</button>
    <button onclick="call('POST','/api/admin/diagnostics/smoke-test')">Smoke Test Comments</button>
    <button onclick="call('POST','/api/admin/diagnostics/create-test-lead', {})">Create Test Lead</button>
  </div>
  <div class="row">
    <label>Tenant ID</label>
    <input type="number" id="tenant_id" placeholder="1">
    <label>Message (для Check Tenant Prompt)</label>
    <input type="text" id="prompt_message" placeholder="Привет">
    <button onclick="testTenantPrompt()">Check Tenant Prompt</button>
  </div>
  <div class="row">
    <label>Chat key (для Mute Test)</label>
    <input type="text" id="chat_key" placeholder="77001234567@s.whatsapp.net">
    <button onclick="testMute()">Mute Chat Test</button>
  </div>
  <div class="row">
    <label>RemoteJid (для Ping ChatFlow)</label>
    <input type="text" id="remote_jid" placeholder="77001234567@s.whatsapp.net">
    <button onclick="pingChatflow()">ChatFlow Webhook Ping</button>
  </div>
  <div class="row">
    <label>Ответ</label>
    <pre id="result">—</pre>
  </div>
  <script>
    function getToken() { return localStorage.getItem('qa_jwt') || document.getElementById('token').value; }
    function saveToken() {
      var t = document.getElementById('token').value.trim();
      if (t) { localStorage.setItem('qa_jwt', t); document.getElementById('result').textContent = 'Token saved.'; }
    }
    function getTenantId() { var v = document.getElementById('tenant_id').value; return v ? parseInt(v, 10) : null; }
    function out(x) { document.getElementById('result').textContent = typeof x === 'string' ? x : JSON.stringify(x, null, 2); }
    async function call(method, path, body) {
      var token = getToken();
      if (!token) { out('Error: set JWT and click Save token'); return; }
      try {
        var opt = { method: method, headers: { 'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json' } };
        if (body && Object.keys(body).length) opt.body = JSON.stringify(body);
        var r = await fetch(path, opt);
        var j = await r.json().catch(function() { return { _raw: await r.text() }; });
        out({ status: r.status, ok: r.ok, body: j });
      } catch (e) { out('Error: ' + e.message); }
    }
    function testTenantPrompt() {
      var tid = getTenantId();
      var msg = document.getElementById('prompt_message').value.trim() || 'Привет';
      if (!tid) { out('Error: enter tenant_id'); return; }
      call('POST', '/api/admin/diagnostics/test-tenant-prompt', { tenant_id: tid, message: msg });
    }
    function testMute() {
      var tid = getTenantId();
      var key = document.getElementById('chat_key').value.trim();
      if (!tid || !key) { out('Error: enter tenant_id and chat_key'); return; }
      call('POST', '/api/admin/diagnostics/test-mute', { tenant_id: tid, chat_key: key });
    }
    function pingChatflow() {
      var tid = getTenantId();
      var jid = document.getElementById('remote_jid').value.trim();
      if (!tid) { out('Error: enter tenant_id'); return; }
      call('POST', '/api/admin/diagnostics/ping-chatflow', { tenant_id: tid, remoteJid: jid || null });
    }
  </script>
</body>
</html>"""


@router.get("/diagnostics/ui", response_class=HTMLResponse, include_in_schema=False)
async def diagnostics_ui(
    current_user: User = Depends(get_current_admin_or_owner),
):
    """QA-панель: проверка диагностик без Postman. Доступ: admin или owner tenant."""
    return QA_UI_HTML


class CreateTestLeadBody(BaseModel):
    tenant_id: Optional[int] = None


@router.post("/diagnostics/create-test-lead", response_model=dict)
async def diagnostics_create_test_lead(
    body: Optional[CreateTestLeadBody] = Body(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner),
):
    """Создать тестовый лид. Если tenant_id не передан — берётся tenant текущего пользователя (owner)."""
    tenant_id = body.tenant_id if body and body.tenant_id is not None else None
    if not tenant_id:
        tenant = await crud.get_tenant_for_me(db, current_user.id)
        if not tenant:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id required or user must have a tenant")
        tenant_id = tenant.id
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    owner_id = getattr(tenant, "default_owner_user_id", None) or current_user.id
    bot_user = await crud.get_or_create_bot_user(db, user_id=f"qa_test_{tenant_id}_{owner_id}", owner_id=owner_id)
    lead = await crud.create_lead(
        db, owner_id=owner_id, bot_user_id=bot_user.id,
        name="QA Test Lead", phone="+77000000000", summary="Created from QA panel", language="ru",
        tenant_id=tenant_id,
    )
    return {"ok": True, "lead_id": lead.id}


class TestTenantPromptBody(BaseModel):
    tenant_id: int
    message: str = "Привет"


@router.post("/diagnostics/test-tenant-prompt", response_model=dict)
async def diagnostics_test_tenant_prompt(
    body: TestTenantPromptBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner),
):
    """Проверить, какой system prompt используется для tenant (tenant.ai_prompt или default). Вызов OpenAI — reply_preview без полного промпта."""
    tenant = await crud.get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    prompt = (getattr(tenant, "ai_prompt", None) or "").strip()
    from app.services.openai_service import SYSTEM_PROMPT
    system_used = prompt or SYSTEM_PROMPT
    using_default = not bool(prompt)
    ai_prompt_len = len(prompt) if prompt else 0
    reply_preview = ""
    try:
        from app.services import openai_service
        msgs = [{"role": "user", "content": body.message[:500]}]
        text, _ = await openai_service.chat_with_gpt(msgs, use_functions=False, system_override=prompt or None)
        reply_preview = (text or "")[:200] + ("..." if len(text or "") > 200 else "")
    except Exception as e:
        reply_preview = f"(error: {type(e).__name__})"
    return {
        "ok": True,
        "using_default_prompt": using_default,
        "ai_prompt_len": ai_prompt_len,
        "reply_preview": reply_preview,
    }


class TestMuteBody(BaseModel):
    tenant_id: int
    chat_key: str


@router.post("/diagnostics/test-mute", response_model=dict)
async def diagnostics_test_mute(
    body: TestMuteBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner),
):
    """Проверить запись mute: выставить true, затем false, вернуть steps."""
    tenant = await crud.get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    steps = []
    try:
        await crud.set_ai_chat_mute(db, body.tenant_id, body.chat_key, is_muted=True, muted_by_user_id=current_user.id)
        steps.append("set mute=true")
        state = await crud.get_ai_chat_mute(db, body.tenant_id, body.chat_key)
        steps.append(f"get_ai_chat_mute after true: {state}")
        await crud.set_ai_chat_mute(db, body.tenant_id, body.chat_key, is_muted=False, muted_by_user_id=current_user.id)
        steps.append("set mute=false")
        state2 = await crud.get_ai_chat_mute(db, body.tenant_id, body.chat_key)
        steps.append(f"get_ai_chat_mute after false: {state2}")
    except Exception as e:
        steps.append(f"error: {type(e).__name__}: {e}")
    return {"ok": True, "steps": steps}


class PingChatflowBody(BaseModel):
    tenant_id: int
    remoteJid: Optional[str] = None


@router.post("/diagnostics/ping-chatflow", response_model=dict)
async def diagnostics_ping_chatflow(
    body: PingChatflowBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_or_owner),
):
    """Проверить привязку ChatFlow у tenant (token/instance_id, active). Секреты не возвращаем — только длина/masked."""
    tenant = await crud.get_tenant_by_id(db, body.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    acc = await crud.get_active_chatflow_account_for_tenant(db, body.tenant_id)
    if not acc:
        return {"ok": False, "binding": None, "note": "No active ChatFlow binding for this tenant"}
    token_len = len(getattr(acc, "chatflow_token", None) or "")
    instance = (getattr(acc, "chatflow_instance_id", None) or "")[:20]
    return {
        "ok": True,
        "binding": {"token_len": token_len, "instance_id_preview": instance + ("..." if len(getattr(acc, "chatflow_instance_id", None) or "") > 20 else "")},
        "note": "Send a real message via WhatsApp to trigger the webhook.",
    }
