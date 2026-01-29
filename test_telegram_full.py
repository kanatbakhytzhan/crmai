"""
Полный тест Telegram уведомления с кнопками
"""
import asyncio
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

TELEGRAM_BOT_TOKEN = "8294649326:AAFPpOUEZDdxuyi-oZHATWofIy21ZbgBZ6E"
TELEGRAM_CHAT_ID = "615605961"

async def test_full_notification():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    
    try:
        text = (
            f"TEST novaya zayavka!\n\n"
            f"Imya: Kanat\n"
            f"Telefon: +77768776637\n"
            f"Zapros: Hochu postroit dom 150 m²\n\n"
            f"Yazyk: Kazahskiy\n"
            f"ID zayavki: #999"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="V rabotu", callback_data="status_process_999")],
            [InlineKeyboardButton(text="Zakryt", callback_data="status_done_999")],
            [InlineKeyboardButton(text="Otkaz", callback_data="status_cancel_999")]
        ])
        
        print("[*] Otpravka polnogo uvedomleniya...")
        message = await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            reply_markup=keyboard
        )
        print(f"[OK] Uvedomlenie otpravleno! Message ID: {message.message_id}")
        print(f"\n=== PROVERITE TELEGRAM ===")
        print(f"Esli ne vidite soobshchenie:")
        print(f"1. Naidte bota @{(await bot.get_me()).username}")
        print(f"2. Napisite emu /start")
        print(f"3. Poprobuite snova")
        
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {str(e)[:300]}")
        
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(test_full_notification())
