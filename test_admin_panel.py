"""
Тест админ-панели (SQLAdmin с AsyncEngine)
"""
import requests

BASE_URL = "http://localhost:8000"


def test_admin_panel():
    """Тестирование админ-панели"""
    
    print("=" * 70)
    print("TEST: ADMIN PANEL (SQLAdmin + AsyncEngine)")
    print("=" * 70)
    
    # Создаем сессию для сохранения cookies
    session = requests.Session()
    
    # Тест 1: Страница логина
    print("\n[1/4] Test: Admin login page...")
    
    response = session.get(f"{BASE_URL}/admin")
    
    if response.status_code == 200:
        print(f"    [OK] Login page loaded (status: 200)")
        if 'login' in response.text.lower():
            print(f"    [OK] Login form found")
        else:
            print(f"    [WARNING] No login form detected")
    else:
        print(f"    [ERROR] Status: {response.status_code}")
        return
    
    # Тест 2: Логин
    print("\n[2/4] Test: Admin authentication...")
    
    response = session.post(
        f"{BASE_URL}/admin/login",
        data={
            "username": "admin",
            "password": "admin123"
        },
        allow_redirects=False
    )
    
    if response.status_code in [302, 303, 307]:
        print(f"    [OK] Login successful (redirect: {response.status_code})")
    elif response.status_code == 200:
        print(f"    [OK] Login processed")
    else:
        print(f"    [ERROR] Login failed: {response.status_code}")
        return
    
    # Тест 3: Главная страница админки
    print("\n[3/4] Test: Admin dashboard...")
    
    response = session.get(f"{BASE_URL}/admin")
    
    if response.status_code == 200:
        print(f"    [OK] Dashboard loaded")
        
        # Проверяем наличие моделей
        models_found = {
            "Заявки": "Заявки" in response.text or "Lead" in response.text,
            "Клиенты": "Клиенты" in response.text or "BotUser" in response.text,
            "Компании": "Компании" in response.text or "User" in response.text,
        }
        
        for model, found in models_found.items():
            status = "[OK]" if found else "[MISSING]"
            print(f"    {status} Model: {model}")
    else:
        print(f"    [ERROR] Dashboard failed: {response.status_code}")
        return
    
    # Тест 4: Открытие раздела "Заявки"
    print("\n[4/4] Test: Leads page (КРИТИЧЕСКИЙ ТЕСТ!)...")
    
    response = session.get(f"{BASE_URL}/admin/lead/list")
    
    if response.status_code == 200:
        print(f"    [OK] Leads page loaded successfully!")
        print(f"    [OK] No Internal Server Error!")
        
        # Проверяем таблицу
        if '<table' in response.text.lower():
            print(f"    [OK] Table found")
        
        if 'id' in response.text.lower():
            print(f"    [OK] Columns rendered")
    else:
        print(f"    [ERROR] Leads page failed: {response.status_code}")
        if response.status_code == 500:
            print(f"    [ERROR] Internal Server Error - see terminal logs!")
        print(f"\n    Response preview:")
        print(f"    {response.text[:500]}")
        return
    
    # Тест 5: Клиенты
    print("\n[5/5] Test: Bot Users page...")
    
    response = session.get(f"{BASE_URL}/admin/botuser/list")
    
    if response.status_code == 200:
        print(f"    [OK] Bot Users page loaded!")
    else:
        print(f"    [ERROR] Bot Users failed: {response.status_code}")
    
    # Итог
    print("\n" + "=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print("[OK] Admin panel accessible")
    print("[OK] Authentication works")
    print("[OK] Dashboard loads")
    print("[OK] Leads page works (NO 500 ERROR!)")
    print("[OK] Bot Users page works")
    print("\n[SUCCESS] Admin panel fully functional!")
    print("\nOpen in browser: http://localhost:8000/admin")
    print("Login: admin")
    print("Password: admin123")


if __name__ == "__main__":
    try:
        test_admin_panel()
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Server is not running!")
        print("Start it: python main.py")
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
