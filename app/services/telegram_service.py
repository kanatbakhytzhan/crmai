"""
Сервис для работы с Telegram Bot API (только отправка уведомлений)
"""
from typing import Optional
from aiogram import Bot

from app.core.config import get_settings

settings = get_settings()

# Инициализация бота
bot = Bot(token=settings.telegram_bot_token)


async def send_lead_notification(
    lead_id: int,
    name: str,
    phone: str,
    summary: str,
    language: str,
    city: str = "",
    object_type: str = "",
    area: str = ""
) -> Optional[int]:
    """
    Отправить уведомление админу о новой заявке
    
    Args:
        lead_id: ID лида в БД
        name: Имя клиента
        phone: Телефон клиента
        summary: Описание запроса
        language: Язык общения
        city: Город
        object_type: Тип объекта
        area: Площадь
        
    Returns:
        message_id отправленного сообщения
    """
    # Формируем текст сообщения с emoji
    text = "🧱 Новая заявка\n\n"
    text += f"👤 Имя: {name}\n"
    text += f"📞 Телефон: {phone}\n"
    
    if city:
        text += f"📍 Город: {city}\n"
    if object_type:
        text += f"🏠 Объект: {object_type}\n"
    if area:
        text += f"📐 Площадь: {area}\n"
    
    if summary:
        text += f"📝 Запрос: {summary}\n"
    
    text += f"\n🆔 ID заявки: #{lead_id}"
    
    try:
        print(f"[Telegram] Otpravka uvedomleniya dlya lida #{lead_id}")
        print(f"[Telegram] Chat ID: {settings.telegram_chat_id}")
        
        # Отправляем сообщение БЕЗ кнопок (для кнопок нужен webhook)
        message = await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text
        )
        
        print(f"[Telegram] Soobshchenie otpravleno! Message ID: {message.message_id}")
        
        return message.message_id
    except Exception as e:
        print(f"[Telegram ERROR] {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return None


async def stop_bot():
    """Остановить бота (закрыть сессию)"""
    await bot.session.close()
