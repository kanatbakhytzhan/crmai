"""
Сервис для работы с OpenAI API (Whisper + GPT-4o)
"""
import json
from typing import List, Dict, Optional, Tuple
from openai import AsyncOpenAI
from app.core.config import get_settings

settings = get_settings()
client = AsyncOpenAI(api_key=settings.openai_api_key)


# Системный промпт для ИИ-менеджера
SYSTEM_PROMPT = """Ты — профессиональный менеджер по продажам строительной компании. Твое имя — Алия.

**КРИТИЧЕСКИ ВАЖНЫЕ ПРАВИЛА:**

1. **Язык общения:** 
   - Ты свободно владеешь Русским и Казахским языком.
   - ОБЯЗАТЕЛЬНО определяй язык пользователя в ПЕРВОМ же сообщении.
   - Если клиент говорит на КАЗАХСКОМ — отвечай ТОЛЬКО на КАЗАХСКОМ.
   - Если клиент говорит на РУССКОМ — отвечай ТОЛЬКО на РУССКОМ.
   - Если клиент смешивает языки — выбери тот язык, на котором больше слов.
   - НЕ МЕНЯЙ язык в середине диалога без причины.

2. **О себе:**
   - Когда спрашивают "как вас зовут?" или "кто вы?" - отвечай: "Меня зовут Алия, я менеджер строительной компании"
   - НЕ пиши "Как я могу помочь?" после представления
   - Просто назови имя и продолжай разговор

3. **Стиль общения:** 
   - Естественный, живой разговор
   - Короткие сообщения (2-3 предложения максимум)
   - Задавай вопросы ПОСТЕПЕННО, по 1 за раз
   - НЕ перегружай клиента информацией
   - Говори как живой человек, не как робот

4. **Процесс квалификации (ВАЖНО - делай это ПОСТЕПЕННО):**
   
   ВАРИАНТ А: Полная квалификация (обычный случай)
   
   Шаг 1: Узнай потребность
   - "Чем могу помочь?"
   - Дождись ответа
   
   Шаг 2: Собери информацию постепенно (один вопрос за раз):
   - В каком городе? (например: Алматы, Астана)
   - Что нужно? (дом, квартира, ремонт - узнай объект)
   - Какая площадь? (в квадратных метрах)
   - Есть ли участок? Когда планируют начать?
   
   Шаг 3: Предложи консультацию
   - "Предлагаю бесплатную консультацию"
   - "Как вас зовут и на какой номер можно перезвонить?"
   
   ВАРИАНТ Б: Быстрая заявка (клиент спешит/хочет звонок сразу)
   
   Если клиент говорит "позвоните мне", "хочу обсудить по телефону", "созвонимся" и т.п.:
   - НЕ задавай много вопросов
   - Сразу: "Хорошо, как вас зовут и на какой номер перезвонить?"
   - Собери МИНИМУМ: имя + телефон (остальное опционально)
   
5. **ЗАПРЕЩЕНО:**
   - ❌ Называть точную цену (всегда говори что цена индивидуальна)
   - ❌ Спрашивать несколько вопросов сразу
   - ❌ Писать длинные сообщения
   - ❌ Сразу предлагать консультацию (сначала квалифицируй)
   - ❌ После получения контактов - НЕ продолжай разговор, просто поблагодари

6. **Когда получил ИМЯ и ТЕЛЕФОН:**
   - Используй функцию `register_lead` ОДИН РАЗ
   - Передай: имя, телефон, краткое резюме, язык (ru/kk)
   - Поблагодари клиента
   - ЗАВЕРШАЙ квалификацию - НЕ задавай больше вопросов о доме
   - Если клиент попрощается после заявки - просто попрощайся вежливо
   - НЕ создавай повторные заявки для одного клиента

7. **Возражения:**
   - "Дорого" → "Какой бюджет рассматриваете? Есть разные варианты"
   - "Подумаю" → "Консультация бесплатная и ни к чему не обязывает"
   - "Перезвоню" → "Консультация займет 15 минут, поможет сориентироваться"

**ПРИМЕРЫ ПРАВИЛЬНОГО ОБЩЕНИЯ:**

Клиент: "Здравствуйте"
Ты: "Здравствуйте! Чем могу помочь?"

Клиент: "Хочу построить дом"
Ты: "Отлично! У вас уже есть участок?"

Клиент: "Да, есть"
Ты: "Где он находится?"

Клиент: "В пригороде Алматы"
Ты: "Хорошо. Какую площадь дома рассматриваете?"

Клиент: "150 квадратов"
Ты: "Предлагаю бесплатную консультацию с архитектором - он рассчитает точную стоимость и сроки. Как вас зовут?"

Клиент: "Алексей"
Ты: "На какой номер вам перезвонить?"

Клиент: "+77001234567"
Ты: "Спасибо, Алексей! Наш менеджер свяжется с вами в ближайшее время."

Клиент: "Спасибо, до свидания"
Ты: "Всего доброго! До связи!"
[КОНЕЦ - заявка УЖЕ создана, просто прощаемся]

**Помни:** Один вопрос за раз. Естественный разговор. После получения контактов - СТОП."""


# Определение функции для Function Calling
FUNCTION_REGISTER_LEAD = {
    "type": "function",
    "function": {
        "name": "register_lead",
        "description": "Регистрация нового лида (заявки клиента) после получения имени и телефона",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Имя клиента"
                },
                "phone": {
                    "type": "string",
                    "description": "Номер телефона клиента"
                },
                "city": {
                    "type": "string",
                    "description": "Город где находится клиент или участок (например: Алматы, Астана, Шымкент)"
                },
                "object_type": {
                    "type": "string",
                    "description": "Тип объекта (дом, үй, квартира, пәтер, коттедж, баня, гараж и т.д.)"
                },
                "area": {
                    "type": "string",
                    "description": "Площадь объекта в м² (например: 150, 100-120, 200 м²)"
                },
                "summary": {
                    "type": "string",
                    "description": "Краткое описание запроса: что именно нужно (строительство, ремонт, отделка), наличие участка, сроки, бюджет"
                },
                "language": {
                    "type": "string",
                    "enum": ["ru", "kk"],
                    "description": "Язык общения с клиентом (ru - русский, kk - казахский)"
                }
            },
            "required": ["name", "phone", "language"]
        }
    }
}


async def transcribe_audio(audio_file_path: str) -> str:
    """
    Транскрибировать аудио в текст через Whisper
    
    Args:
        audio_file_path: Путь к аудио файлу
        
    Returns:
        Распознанный текст
    """
    try:
        print(f"[Whisper] Otkrytie faila: {audio_file_path}")
        with open(audio_file_path, "rb") as audio_file:
            print(f"[Whisper] Otpravka zaprosa v OpenAI...")
            transcription = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
                # language НЕ указываем - пусть Whisper сам определяет язык (RU/KK)
            )
            print(f"[Whisper] Uspeshno raspoznano (length: {len(transcription.text)})")
        return transcription.text
    except Exception as e:
        error_str = str(e).lower()
        print(f"[Whisper ERROR] {type(e).__name__}")
        # Проверяем типичные ошибки
        if "authentication" in error_str or "api_key" in error_str:
            raise Exception("Nepravilnyy OpenAI API klyuch")
        elif "file" in error_str or "format" in error_str:
            raise Exception("Nepodderzhivaemyy format faila")
        elif "quota" in error_str or "insufficient" in error_str:
            raise Exception("Prevyshen limit OpenAI API")
        else:
            raise Exception("Oshibka raspoznavaniya audio")


async def chat_with_gpt(
    messages: List[Dict[str, str]],
    use_functions: bool = True
) -> Tuple[str, Optional[Dict]]:
    """
    Отправить сообщения в GPT-4o и получить ответ
    
    Args:
        messages: История сообщений в формате OpenAI
        use_functions: Использовать ли Function Calling
        
    Returns:
        Tuple: (текст ответа, данные function_call если есть)
    """
    try:
        # Добавляем системный промпт в начало
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        
        print(f"[GPT] Otpravka {len(full_messages)} soobshcheniy")
        
        # Параметры запроса
        request_params = {
            "model": "gpt-4o",
            "messages": full_messages,
            "temperature": 0.7,
            "max_tokens": 500
        }
        
        # Добавляем функции, если нужно
        if use_functions:
            request_params["tools"] = [FUNCTION_REGISTER_LEAD]
            request_params["tool_choice"] = "auto"
        
        # Делаем запрос
        print(f"[GPT] Zapros k OpenAI...")
        response = await client.chat.completions.create(**request_params)
        
        message = response.choices[0].message
        
        # Проверяем, вызвана ли функция
        if message.tool_calls:
            print(f"[GPT] Function call obnaruzheno")
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            return "", {"name": function_name, "arguments": function_args}
        
        # Обычный текстовый ответ
        print(f"[GPT] Polucheno tekstovoe soobshchenie")
        return message.content, None
        
    except Exception as e:
        error_str = str(e).lower()
        print(f"[GPT ERROR] {type(e).__name__}")
        # Проверяем типичные ошибки
        if "authentication" in error_str or "api_key" in error_str:
            raise Exception("Nepravilnyy OpenAI API klyuch")
        elif "quota" in error_str or "insufficient" in error_str:
            raise Exception("Prevyshen limit OpenAI API")
        elif "rate_limit" in error_str:
            raise Exception("Slishkom mnogo zaprosov, poprobuite pozzhe")
        elif "model" in error_str:
            raise Exception("Model GPT-4o nedostupna")
        else:
            raise Exception("Oshibka obrabotki zaprosa")


def format_messages_for_gpt(messages: List[Dict]) -> List[Dict[str, str]]:
    """
    Форматировать историю сообщений из БД для OpenAI API
    
    Args:
        messages: Список сообщений из БД (Message objects)
        
    Returns:
        Список в формате OpenAI
    """
    # Берем последние N сообщений и переворачиваем (от старых к новым)
    formatted = []
    for msg in reversed(messages):
        formatted.append({
            "role": msg.role,
            "content": msg.content
        })
    return formatted
