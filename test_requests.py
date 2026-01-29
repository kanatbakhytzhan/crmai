"""
Скрипт для тестирования API (альтернатива Swagger UI)
"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_text_message():
    """Тест отправки текстового сообщения"""
    print("\n" + "="*50)
    print("🧪 ТЕСТ: Отправка текстового сообщения")
    print("="*50)
    
    url = f"{BASE_URL}/api/chat"
    data = {
        "user_id": "test_user_1",
        "message_text": "Здравствуйте! Хочу построить дом"
    }
    
    response = requests.post(url, data=data)
    result = response.json()
    
    print(f"\n✅ Статус: {response.status_code}")
    print(f"📝 Ответ бота:\n{result.get('response', 'Нет ответа')}\n")
    
    return result


def test_conversation_flow():
    """Тест полного цикла диалога с регистрацией лида"""
    print("\n" + "="*50)
    print("🧪 ТЕСТ: Полный цикл диалога")
    print("="*50)
    
    messages = [
        "Здравствуйте",
        "У меня есть участок в пригороде Алматы",
        "Хочу дом примерно 150 квадратных метров",
        "Планирую начать строительство весной",
        "Бюджет около 30 миллионов тенге",
        "Да, хочу записаться на консультацию. Меня зовут Алексей, мой телефон +77001234567"
    ]
    
    user_id = "test_user_conversation"
    url = f"{BASE_URL}/api/chat"
    
    for i, message in enumerate(messages, 1):
        print(f"\n--- Сообщение {i} ---")
        print(f"👤 Клиент: {message}")
        
        data = {
            "user_id": user_id,
            "message_text": message
        }
        
        response = requests.post(url, data=data)
        result = response.json()
        
        print(f"🤖 Алия: {result.get('response', 'Нет ответа')}")
        
        if result.get("lead_created"):
            print("\n🎉 ЛИД СОЗДАН! Проверьте Telegram - должно прийти уведомление.")
            break
        
        import time
        time.sleep(1)  # Небольшая задержка между сообщениями


def test_get_history():
    """Тест получения истории диалога"""
    print("\n" + "="*50)
    print("🧪 ТЕСТ: Получение истории диалога")
    print("="*50)
    
    user_id = "test_user_1"
    url = f"{BASE_URL}/api/user/{user_id}/history"
    
    response = requests.get(url)
    result = response.json()
    
    print(f"\n✅ Статус: {response.status_code}")
    print(f"📚 Количество сообщений: {len(result.get('messages', []))}")
    
    messages = result.get('messages', [])
    if messages:
        print("\n--- Последние 5 сообщений ---")
        for msg in messages[-5:]:
            role = "👤 Клиент" if msg['role'] == 'user' else "🤖 Алия"
            print(f"\n{role}: {msg['content'][:100]}...")


def test_health():
    """Проверка работоспособности API"""
    print("\n" + "="*50)
    print("🧪 ТЕСТ: Health Check")
    print("="*50)
    
    url = f"{BASE_URL}/api/health"
    response = requests.get(url)
    result = response.json()
    
    print(f"\n✅ Статус: {response.status_code}")
    print(f"💚 Ответ: {json.dumps(result, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║        🧪 ТЕСТИРОВАНИЕ AI SALES MANAGER API              ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    try:
        # 1. Health check
        test_health()
        
        # 2. Простое сообщение
        test_text_message()
        
        # 3. Получение истории
        test_get_history()
        
        # 4. Полный цикл диалога (раскомментируйте если хотите протестировать)
        # print("\n\n⚠️  Сейчас будет запущен полный цикл диалога с созданием лида.")
        # print("Продолжить? (y/n): ", end="")
        # if input().lower() == 'y':
        #     test_conversation_flow()
        
        print("\n\n✅ Все тесты завершены!")
        print("💡 Для запуска полного цикла раскомментируйте код выше.\n")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ОШИБКА: Не удается подключиться к API")
        print("Убедитесь, что сервер запущен: python main.py\n")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}\n")
