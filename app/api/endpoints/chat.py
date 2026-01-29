"""
API эндпоинты для чата с AI
"""
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.api.deps import get_db, get_current_user
from app.database import crud
from app.database.models import User
from app.services import openai_service, telegram_service

router = APIRouter()


@router.post("/chat")
async def chat(
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
            # Гостевой режим - используем первого пользователя в системе
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
        
        # 3. Сохраняем сообщение клиента в БД
        print(f"[*] Sohranenie soobshcheniya v BD (length: {len(message_text)})")
        await crud.create_message(db, bot_user.id, "user", message_text)
        
        # 4. Получаем историю диалога
        history = await crud.get_bot_user_messages(db, bot_user.id, limit=20)
        messages = openai_service.format_messages_for_gpt(history)
        print(f"[*] Zagruzhenno soobshcheniy iz istorii: {len(messages)}")
        
        # 5. Отправляем в GPT-4o
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
        
        # 6. Обрабатываем Function Call (если есть)
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
                print(f"[OK] Lid sozdan s ID: {lead.id} (owner: {owner_id})")
                
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
        
        # 7. Сохраняем ответ бота в БД
        if response_text:
            await crud.create_message(db, bot_user.id, "assistant", response_text)
        
        # 8. Возвращаем ответ
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
    Получить все заявки текущего пользователя
    
    Требует JWT токен. Возвращает ТОЛЬКО заявки владельца токена.
    Multi-tenancy: Пользователь А не видит заявки Пользователя Б.
    """
    leads = await crud.get_user_leads(db, owner_id=current_user.id)
    return {"leads": leads, "total": len(leads)}


@router.get("/leads/{lead_id}")
async def get_lead(
    lead_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Получить одну заявку по ID
    
    Требует JWT токен. Возвращает заявку только если она принадлежит владельцу токена.
    """
    lead = await crud.get_lead_by_id(db, lead_id=lead_id, owner_id=current_user.id)
    
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=f"Lead with ID {lead_id} not found"
        )
    
    return lead


@router.patch("/leads/{lead_id}")
async def update_lead_status(
    lead_id: int,
    status_update: dict,  # Принимаем {"status": "new" | "in_progress" | "success" | "failed"}
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Обновить статус заявки
    
    Требует JWT токен. Обновляет заявку только если она принадлежит владельцу токена.
    
    Допустимые статусы:
    - `new` - Новая заявка
    - `in_progress` - В работе
    - `success` - Успешно завершена
    - `failed` - Отказ/не удалось
    
    Пример запроса:
    ```json
    {
      "status": "in_progress"
    }
    ```
    """
    # Валидация статуса
    allowed_statuses = ["new", "in_progress", "success", "failed"]
    new_status_str = status_update.get("status")
    
    if not new_status_str or new_status_str not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(allowed_statuses)}"
        )
    
    # Конвертируем в LeadStatus enum
    from app.database.models import LeadStatus
    status_mapping = {
        "new": LeadStatus.NEW,
        "in_progress": LeadStatus.IN_PROGRESS,
        "success": LeadStatus.DONE,  # "success" → DONE
        "failed": LeadStatus.CANCELLED  # "failed" → CANCELLED
    }
    
    new_status = status_mapping[new_status_str]
    
    # Обновляем статус
    lead = await crud.update_lead_status(
        db, 
        lead_id=lead_id, 
        owner_id=current_user.id, 
        status=new_status
    )
    
    if not lead:
        raise HTTPException(
            status_code=404,
            detail=f"Lead with ID {lead_id} not found"
        )
    
    print(f"[OK] Lead #{lead_id} status updated: {new_status_str} (by user {current_user.id})")
    
    return {
        "status": "success",
        "message": f"Lead status updated to {new_status_str}",
        "lead": lead
    }


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
    deleted = await crud.delete_lead(db, lead_id=lead_id, owner_id=current_user.id)
    
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
