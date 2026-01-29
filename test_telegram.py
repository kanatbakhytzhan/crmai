"""
Тест отправки Telegram уведомления
"""
import asyncio
from aiogram import Bot

# Ваши данные
TELEGRAM_BOT_TOKEN = "8294649326:AAFPpOUEZDdxuyi-oZHATWofIy21ZbgBZ6E"
TELEGRAM_CHAT_ID = "615605961"

async def test_telegram():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    try:
        # Попытка отправить тестовое сообщение
        print("[*] Otpravka testovoho soobshcheniya v Telegram...")
        message = await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="TEST: Proverka raboty Telegram bota"
        )
        print(f"[OK] Soobshchenie otpravleno! Message ID: {message.message_id}")
        
    except Exception as e:
        print(f"[ERROR] Oshibka: {type(e).__name__}")
        print(f"[ERROR] Details: {str(e)[:200]}")
        
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_telegram())
