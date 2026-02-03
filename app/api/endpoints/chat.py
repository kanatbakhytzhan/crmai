"""
API эндпоинты для чата с AI
Unified conversation history: DB-backed per (channel, external_id). Web channel uses email or guest:<ip>.
"""
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.core.config import get_settings
from app.database import crud
from app.database.models import User
from app.schemas.lead import (
    LeadResponse,
    LeadCommentCreate,
    LeadCommentResponse,
    AIMuteUpdate,
    LeadAssignBody,
    LeadBulkAssignBody,
    LeadPatchBody,
)
from app.services import openai_service, telegram_service, conversation_service

router = APIRouter()


@router.post("/chat")
async def chat(
    request: Request,
    user_id: str = Form(...),  # ID клиента (session_id для гостей)
    text: Optional[str] = Form(None),
    audio_file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(lambda: None)  # Токен опциональный!
):
    """
    Обработка сообщения от клиента (текст или аудио)
    
    ПУБЛИЧНЫЙ ЭНДПОИНТ:
    - Работает БЕЗ токена (для гостей на сайте)
    - Работает С токеном (для владельцев в мобильном приложении)
    
    Гостевой режим (Guest Mode):
    - Если токена нет → используется дефолтный owner_id=1
    - Все заявки от сайта попадают первому зарегистрированному пользователю
    
    Args:
        user_id: ID клиента (session_id для веб-интерфейса)
        text: Текстовое сообщение (опционально)
        audio_file: Аудио файл (опционально)
        current_user: Авторизованный пользователь (опционально, из JWT токена)
        
    Returns:
        Ответ от AI бота
    """
    try:
        # Определяем владельца (owner)
        if current_user:
            # Если есть JWT токен - используем владельца из токена
            owner_id = current_user.id
            owner_name = current_user.company_name
            print(f"\n[*] Novoe soobshchenie ot user_id: {user_id}")
            print(f"[*] Owner ID: {owner_id} ({owner_name}) [Authenticated]")
        else:
            # Гостевой режим: DEFAULT_OWNER_EMAIL (если задан) или первый пользователь в БД
            from app.core.config import get_settings
            settings = get_settings()
            default_email = getattr(settings, "default_owner_email", None)
            if default_email:
                first_user = await crud.get_user_by_email(db, email=default_email)
                if not first_user:
                    print(f"[WARNING] DEFAULT_OWNER_EMAIL={default_email} ne nayden v BD, fallback na get_first_user()")
                    first_user = await crud.get_first_user(db)
            else:
                first_user = await crud.get_first_user(db)
            if not first_user:
                raise HTTPException(
                    status_code=500,
                    detail="No users found. Please register first user via API."
                )
            owner_id = first_user.id
            owner_name = first_user.company_name
            print(f"\n[*] Novoe soobshchenie ot user_id: {user_id}")
            print(f"[*] Owner ID: {owner_id} ({owner_name}) [Guest - Web Interface]")
        
        # 1. Получаем или создаем клиента бота
        bot_user = await crud.get_or_create_bot_user(db, user_id, owner_id=owner_id)
        print(f"[*] BotUser ID: {bot_user.id}")
        
        # 2. Обрабатываем входящее сообщение
        message_text = text or ""
        
        if audio_file:
            print(f"[*] Obrabotka audio faila")
            print(f"[*] Content-Type: {audio_file.content_type}")
            
            # Сохраняем временный файл
            file_ext = os.path.splitext(audio_file.filename)[1] or ".ogg"
            print(f"[*] Rasshirenie faila: {file_ext}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
                content = await audio_file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name
            
            print(f"[*] Vremennyy fail sohranyon: {tmp_file_path}")
            print(f"[*] Razmer faila: {len(content)} bytes")
            
            try:
                # Транскрибируем аудио
                print(f"[*] Otpravka v Whisper API...")
                message_text = await openai_service.transcribe_audio(tmp_file_path)
                print(f"[OK] Transkribirovano (length: {len(message_text)})")
            except Exception as e:
                print(f"[ERROR] Oshibka Whisper: {type(e).__name__}")
                import traceback
                traceback.print_exc()
                raise HTTPException(
                    status_code=400,
                    detail="Ne udalos raspoznat audio. Poprobuite otpravit tekstom."
                )
            finally:
                if os.path.exists(tmp_file_path):
                    os.remove(tmp_file_path)
                    print(f"[*] Vremennyy fail udalen")
        
        # 3. Conversation history (unified engine): identify session
        if current_user:
            external_id = current_user.email or str(current_user.id)
        else:
            client_host = getattr(request.client, "host", None) or "unknown"
            external_id = f"guest:{client_host}"
        conv = await conversation_service.get_or_create_conversation(
            db, tenant_id=None, channel="web", external_id=external_id, phone_number_id=None
        )
        await conversation_service.append_user_message(db, conv.id, message_text)
        messages = await conversation_service.build_context_messages(db, conv.id, limit=20)
        print(f"[*] Zagruzhenno soobshcheniy iz istorii (conv_id={conv.id}): {len(messages)}")

        # 4. Отправляем в GPT-4o
        print(f"[*] Otpravka v GPT-4o...")
        try:
            response_text, function_call = await openai_service.chat_with_gpt(messages)
            print(f"[OK] Polucheno ot GPT (length: {len(response_text) if response_text else 0}, function: {bool(function_call)})")
        except Exception as e:
            print(f"[ERROR] Oshibka GPT: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail="Izvините, proisoshla oshibka. Poprobuite eshe raz."
            )

        # 5. Обрабатываем Function Call (если есть)
        if function_call and function_call["name"] == "register_lead":
            print(f"[*] Function call: register_lead")
            args = function_call["arguments"]
            print(f"[*] Argumenty polucheny (keys: {list(args.keys())})")
            
            # ПРОВЕРКА: есть ли уже недавняя заявка (за последние 5 минут)?
            if await crud.has_recent_lead(db, bot_user.id, minutes=5):
                print(f"[WARNING] U klien ta uzhe est nedavnyaya zayavka - propuskaem sozdanie")
                # Просто отвечаем что заявка уже принята
                if args.get("language") == "kk":
                    response_text = "Сіздің өтінішіңіз қабылданды! Менеджер жақын арада хабарласады."
                else:
                    response_text = "Ваша заявка уже принята! Менеджер свяжется в ближайшее время."
            else:
                # Обновляем информацию о клиенте бота
                await crud.update_bot_user_info(
                    db, 
                    user_id=user_id, 
                    owner_id=owner_id,
                    name=args.get("name"), 
                    phone=args.get("phone")
                )
                
                # Создаем лид
                lead = await crud.create_lead(
                    db=db,
                    owner_id=owner_id,  # Владелец (из токена или дефолт)
                    bot_user_id=bot_user.id,
                    name=args["name"],
                    phone=args["phone"],
                    city=args.get("city", ""),
                    object_type=args.get("object_type", ""),
                    area=args.get("area", ""),
                    summary=args.get("summary", "Быстрая заявка - требуется связаться"),
                    language=args["language"]
                )
                # Диагностика: лид создан с owner_id и status=new — должен попасть в GET /api/leads для этого владельца
                print(f"[OK] Lid sozdan: id={lead.id}, owner_id={lead.owner_id}, status={getattr(lead.status, 'value', lead.status)}")
                
                # Отправляем уведомление в Telegram
                try:
                    await telegram_service.send_lead_notification(
                        lead_id=lead.id,
                        name=args["name"],
                        phone=args["phone"],
                        summary=args.get("summary", ""),
                        language=args["language"],
                        city=args.get("city", ""),
                        object_type=args.get("object_type", ""),
                        area=args.get("area", "")
                    )
                    print(f"[OK] Uvedomlenie v Telegram otpravleno")
                except Exception as e:
                    print(f"[WARNING] Oshibka otpravki v Telegram: {type(e).__name__}")
                
                # Генерируем финальное сообщение клиенту
                if args["language"] == "kk":
                    response_text = (
                        f"Рахмет, {args['name']}! Сіздің өтінішіңіз қабылданды. "
                        f"Біздің менеджер жақын арада {args['phone']} нөміріне хабарласады."
                    )
                else:
                    response_text = (
                        f"Спасибо, {args['name']}! Наш менеджер свяжется с вами "
                        f"по номеру {args['phone']} в ближайшее время."
                    )
        
        # 6. Сохраняем ответ в conversation (unified history)
        if response_text:
            await conversation_service.append_assistant_message(db, conv.id, response_text)

        # 7. Возвращаем ответ
        print(f"[OK] Uspeshno obrabotano\n")
        return {
            "status": "success",
            "user_id": user_id,
            "response": response_text,
            "function_called": function_call["name"] if function_call else None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] Neobrabotannaya oshibka: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )


@router.get("/leads")
async def get_leads(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить заявки: owner/rop — все лиды tenant; manager — только назначенные себе.
    Поля: assigned_user_id, assigned_user_email, assigned_user_name, tenant_id, lead_number, next_call_at, last_contact_at.
    """
    settings = get_settings()
    multitenant = (getattr(settings, "multitenant_enabled", "false") or "false").upper() == "TRUE"
    if multitenant:
        leads = await crud.get_leads_for_user_crm(db, user_id=current_user.id)
    else:
        leads = await crud.get_user_leads(db, owner_id=current_user.id, multitenant_include_tenant_leads=False)
    leads_data = []
    for l in leads:
        item = LeadResponse.model_validate(l).model_dump()
        last_c = await crud.get_last_lead_comment(db, l.id)
        item["last_comment"] = (last_c.text[:100] if last_c and last_c.text else None) if last_c else None
        aid = getattr(l, "assigned_user_id", None)
        if aid:
            u = await crud.get_user_by_id(db, aid)
            if u:
                item["assigned_user_email"] = u.email
                item["assigned_user_name"] = getattr(u, "company_name", None)
        leads_data.append(item)
    return {"leads": leads_data, "total": len(leads_data)}


@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить одну заявку по ID. Доступ по ролям: owner/rop — все лиды tenant; manager — только назначенные.
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(
        db, lead_id=lead_id, owner_id=current_user.id,
        multitenant_include_tenant_leads=multitenant,
    )
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead with ID {lead_id} not found")
    item = LeadResponse.model_validate(lead).model_dump()
    aid = getattr(lead, "assigned_user_id", None)
    if aid:
        u = await crud.get_user_by_id(db, aid)
        if u:
            item["assigned_user_email"] = u.email
            item["assigned_user_name"] = getattr(u, "company_name", None)
    return item


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: int,
    body: LeadPatchBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Обновить лид: status, next_call_at, last_contact_at, assigned_user_id (owner/rop).
    Manager может менять только status и next_call_at у своих лидов.
    Обратная совместимость: передавайте только status как раньше.
    """
    from app.database.models import LeadStatus
    status_map = {
        "new": LeadStatus.NEW,
        "in_progress": LeadStatus.IN_PROGRESS,
        "success": LeadStatus.DONE,
        "failed": LeadStatus.CANCELLED,
        "done": LeadStatus.DONE,
        "cancelled": LeadStatus.CANCELLED,
    }
    new_status = None
    if body.status is not None:
        new_status = status_map.get((body.status or "").strip().lower())
        if new_status is None:
            raise HTTPException(status_code=400, detail="Invalid status. Allowed: new, in_progress, success, failed, done, cancelled")
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.update_lead_fields(
        db,
        lead_id=lead_id,
        current_user_id=current_user.id,
        status=new_status,
        next_call_at=body.next_call_at,
        last_contact_at=body.last_contact_at,
        assigned_user_id=body.assigned_user_id,
        multitenant_include_tenant_leads=multitenant,
    )
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead with ID {lead_id} not found")
    return {"ok": True, "lead": LeadResponse.model_validate(lead).model_dump()}


@router.patch("/leads/{lead_id}/assign", response_model=dict)
async def assign_lead(
    lead_id: int,
    body: LeadAssignBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Назначить лид (owner/rop). Manager — 403.
    Body: { "assigned_user_id": 123 | null, "status": "in_progress" (опционально) }.
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if not lead.tenant_id:
        raise HTTPException(status_code=400, detail="Lead has no tenant_id")
    role = await crud.get_tenant_user_role(db, lead.tenant_id, current_user.id)
    if role not in ("owner", "rop"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owner or rop can assign leads")
    status_enum = None
    if body.status:
        from app.database.models import LeadStatus
        status_map = {"new": LeadStatus.NEW, "in_progress": LeadStatus.IN_PROGRESS, "success": LeadStatus.DONE, "failed": LeadStatus.CANCELLED, "done": LeadStatus.DONE, "cancelled": LeadStatus.CANCELLED}
        status_enum = status_map.get((body.status or "").strip().lower())
    updated = await crud.update_lead_assignment(
        db, lead_id, current_user.id, body.assigned_user_id, status=status_enum, multitenant_include_tenant_leads=multitenant
    )
    if not updated:
        raise HTTPException(status_code=400, detail="Assignment failed (user not in tenant or invalid)")
    return {"ok": True, "lead": LeadResponse.model_validate(updated).model_dump()}


@router.post("/leads/assign/bulk", response_model=dict)
async def bulk_assign_leads(
    body: LeadBulkAssignBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Массовое назначение. owner/rop. Возвращает assigned, skipped, skipped_ids.
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    from app.database.models import LeadStatus
    status_map = {"new": LeadStatus.NEW, "in_progress": LeadStatus.IN_PROGRESS, "success": LeadStatus.DONE, "failed": LeadStatus.CANCELLED, "done": LeadStatus.DONE, "cancelled": LeadStatus.CANCELLED}
    set_status = None
    if body.set_status:
        set_status = status_map.get((body.set_status or "").strip().lower())
    assigned, skipped, skipped_ids = await crud.bulk_assign_leads(
        db, body.lead_ids, body.assigned_user_id, current_user.id, set_status=set_status, multitenant_include_tenant_leads=multitenant
    )
    return {"ok": True, "assigned": assigned, "skipped": skipped, "skipped_ids": skipped_ids}


@router.delete("/leads/{lead_id}")
async def delete_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Удалить заявку по ID
    
    Требует JWT токен. Удаляет заявку только если она принадлежит владельцу токена.
    Используется для удаления тестовых/мусорных заявок.
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    deleted = await crud.delete_lead(
        db, lead_id=lead_id, owner_id=current_user.id,
        multitenant_include_tenant_leads=multitenant,
    )
    
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Lead with ID {lead_id} not found"
        )
    
    print(f"[OK] Lead #{lead_id} deleted (by user {current_user.id})")
    
    return {
        "status": "success",
        "message": f"Lead {lead_id} deleted successfully"
    }


@router.get("/leads/{lead_id}/ai-status", response_model=dict)
async def get_lead_ai_status(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Статус AI для чата лида: ai_enabled_global (tenant), ai_muted_in_chat (per-chat mute).
    Требует JWT. Доступ: владелец лида или пользователь tenant.
    remote_jid берётся из lead.bot_user.user_id (для ChatFlow).
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    tenant_id = getattr(lead, "tenant_id", None)
    if tenant_id is None:
        return {"ai_enabled_global": True, "ai_muted_in_chat": False}
    bot_user = await crud.get_bot_user_by_id(db, lead.bot_user_id)
    remote_jid = (bot_user.user_id if bot_user else "") or ""
    tenant = await crud.get_tenant_by_id(db, tenant_id)
    ai_enabled_global = getattr(tenant, "ai_enabled", True) if tenant else True
    chat_enabled = await crud.get_chat_ai_state(db, tenant_id, remote_jid)
    ai_muted_in_chat = not chat_enabled
    return {"ai_enabled_global": ai_enabled_global, "ai_muted_in_chat": ai_muted_in_chat}


@router.post("/leads/{lead_id}/ai-mute", response_model=dict)
async def post_lead_ai_mute(
    lead_id: int,
    body: AIMuteUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Включить/выключить AI в чате лида (per-chat mute). Upsert в chat_ai_states по (tenant_id, remote_jid).
    body: { "muted": true/false }. remote_jid = lead.bot_user.user_id.
    Требует JWT. Доступ: владелец лида или пользователь tenant.
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    tenant_id = getattr(lead, "tenant_id", None)
    bot_user = await crud.get_bot_user_by_id(db, lead.bot_user_id)
    remote_jid = (bot_user.user_id if bot_user else "") or ""
    if tenant_id is None:
        resolved = await crud.resolve_lead_tenant_id(db, lead)
        if resolved is not None:
            lead.tenant_id = resolved
            await db.commit()
            await db.refresh(lead)
            tenant_id = resolved
        else:
            raise HTTPException(
                status_code=422,
                detail={
                    "detail": "Lead has no tenant_id",
                    "hint": "Run admin fix-leads-tenant or re-create lead through tenant-bound webhook",
                    "lead_id": lead_id,
                    "remoteJid": remote_jid or None,
                },
            )
    if not remote_jid:
        raise HTTPException(status_code=400, detail="Lead has no remote_jid (bot_user.user_id)")
    await crud.set_chat_ai_state(db, tenant_id, remote_jid, enabled=not body.muted)
    return {"ok": True, "muted": body.muted}


@router.get("/leads/{lead_id}/comments", response_model=dict)
async def get_lead_comments(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Список комментариев к лиду.
    Требует JWT. Доступ только к своим лидам (или лидам tenant).
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    comments = await crud.get_lead_comments(db, lead_id=lead_id)
    items = [LeadCommentResponse.model_validate(c) for c in comments]
    return {"comments": items, "total": len(items)}


@router.post("/leads/{lead_id}/comments", response_model=LeadCommentResponse, status_code=status.HTTP_201_CREATED)
async def create_lead_comment(
    lead_id: int,
    body: LeadCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Добавить комментарий к лиду.
    Требует JWT. Доступ только к своим лидам (или лидам tenant).
    """
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    comment = await crud.create_lead_comment(db, lead_id=lead_id, user_id=current_user.id, text=body.text)
    return comment


@router.delete("/leads/comments/{comment_id}")
async def delete_lead_comment(
    comment_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Удалить комментарий по ID.
    Требует JWT. Доступ только если лид комментария принадлежит пользователю (или tenant).
    """
    comment = await crud.get_lead_comment_by_id(db, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    multitenant = (getattr(get_settings(), "multitenant_enabled", "false") or "false").upper() == "TRUE"
    lead = await crud.get_lead_by_id(db, comment.lead_id, current_user.id, multitenant_include_tenant_leads=multitenant)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await crud.delete_lead_comment(db, comment_id)
    return {"ok": True}
