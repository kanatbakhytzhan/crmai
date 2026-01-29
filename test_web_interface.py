"""
Тест веб-интерфейса (Guest Mode)
"""
import requests

BASE_URL = "http://localhost:8000"


def test_web_interface():
    """Тестирование публичного веб-интерфейса"""
    
    print("=" * 70)
    print("TEST: WEB INTERFACE (GUEST MODE)")
    print("=" * 70)
    
    # Шаг 1: Проверка главной страницы
    print("\n[1/3] Proverka glavnoy stranitsy (GET /)...")
    
    response = requests.get(f"{BASE_URL}/")
    
    if response.status_code == 200:
        print(f"    [OK] Stranitsa dostupna")
        if 'AI Sales Manager' in response.text:
            print(f"    [OK] HTML soderzhit pravilnyy zagolovok")
        else:
            print(f"    [WARNING] HTML mozhet byt nekorrektnym")
    else:
        print(f"    [ERROR] Status: {response.status_code}")
        return
    
    # Шаг 2: Тест публичного API (БЕЗ токена!)
    print("\n[2/3] Test publichnogo API (BEZ tokena)...")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        data={
            "user_id": "web_guest_test_123",
            "text": "Здравствуйте, хочу узнать о строительстве дома"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"    [OK] API otvetil BEZ tokena!")
        print(f"    Status: {data['status']}")
        print(f"    Response: {data.get('response', 'N/A')[:80]}...")
    else:
        print(f"    [ERROR] Status: {response.status_code}")
        print(f"    {response.text}")
        return
    
    # Шаг 3: Проверка что заявка создается
    print("\n[3/3] Proverka sozdaniya zayavki cherez web...")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        data={
            "user_id": "web_guest_test_456",
            "text": "Хочу дом в Алматы, 150 квадратов, звоните Иван, 87771234567"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"    [OK] Soobshchenie obrabotano")
        print(f"    Function called: {data.get('function_called', 'None')}")
        
        if data.get('function_called') == 'register_lead':
            print(f"    [OK] ZAYAVKA SOZDANA! (dolzhna byt v adminke)")
    else:
        print(f"    [ERROR] Status: {response.status_code}")
    
    # Итог
    print("\n" + "=" * 70)
    print("ITOG:")
    print("=" * 70)
    print("[OK] GET / - Web interface dostupnen")
    print("[OK] POST /api/chat (BEZ tokena) - Rabotaet!")
    print("[OK] Guest Mode - Aktivirovan")
    print("\nOtkroyte v brauzere: http://localhost:8000/")
    print("Ili s telefona:       http://192.168.0.10:8000/")


if __name__ == "__main__":
    try:
        test_web_interface()
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Server ne zapushchen!")
        print("Zapustite: python main.py")
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
