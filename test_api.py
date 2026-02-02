"""
Скрипт для тестирования API
"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_auth_flow():
    """Тестирование авторизации"""
    print("=" * 60)
    print("TEST 1: REGISTRATSIYA")
    print("=" * 60)
    
    # Регистрация
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": "demo@company.kz",
            "password": "demo123",
            "company_name": "Demo Company"
        }
    )
    
    if response.status_code == 201:
        print("[OK] Polzovatel sozdan:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    elif response.status_code == 400:
        print("[INFO] Email uzhe zaregistrirovan")
    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(response.text)
    
    print("\n" + "=" * 60)
    print("TEST 2: LOGIN")
    print("=" * 60)
    
    # Логин
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": "demo@company.kz",
            "password": "demo123"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data["access_token"]
        print(f"[OK] Token poluchon:")
        print(f"    Token: {token[:50]}...")
        return token
    else:
        print(f"[ERROR] Login failed: {response.status_code}")
        print(response.text)
        return None


def test_chat_flow(token):
    """Тестирование чата с JWT"""
    print("\n" + "=" * 60)
    print("TEST 3: CHAT (s JWT tokenom)")
    print("=" * 60)
    
    # Отправка сообщения
    response = requests.post(
        f"{BASE_URL}/api/chat",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "user_id": "test_client_123",
            "text": "Хочу построить дом в Алматы"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Otvet poluchon:")
        print(f"    Status: {data['status']}")
        print(f"    Response: {data.get('response', 'N/A')[:100]}...")
    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(response.text)
    
    print("\n" + "=" * 60)
    print("TEST 4: POLUCHENIE ZAYAVOK")
    print("=" * 60)
    
    # Получение заявок
    response = requests.get(
        f"{BASE_URL}/api/leads",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"[OK] Zayavki polucheny:")
        print(f"    Total: {data['total']}")
        if data['leads']:
            for lead in data['leads'][:3]:
                print(f"    - Lead #{lead['id']}: {lead['name']} ({lead['phone']})")
    else:
        print(f"[ERROR] Status: {response.status_code}")
        print(response.text)


def test_multi_tenancy():
    """Тестирование multi-tenancy"""
    print("\n" + "=" * 60)
    print("TEST 5: MULTI-TENANCY (izolatsiya dannyh)")
    print("=" * 60)
    
    # Создаем второго пользователя
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": "company2@test.kz",
            "password": "pass123",
            "company_name": "Company 2"
        }
    )
    
    if response.status_code in [200, 201]:
        print("[OK] Company 2 sozdana")
    else:
        print("[INFO] Company 2 uzhe sushchestvuet")
    
    # Логин Company 2
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": "company2@test.kz",
            "password": "pass123"
        }
    )
    
    if response.status_code == 200:
        token2 = response.json()["access_token"]
        print(f"[OK] Company 2 zaloginilas")
        
        # Проверяем заявки Company 2
        response = requests.get(
            f"{BASE_URL}/api/leads",
            headers={"Authorization": f"Bearer {token2}"}
        )
        
        if response.status_code == 200:
            total = response.json()["total"]
            print(f"[OK] Company 2 zayavok: {total}")
            if total == 0:
                print("    [OK] IZOLATSIYA RABOTAET! Company 2 ne vidit zayavki Company 1!")


def test_tenant_users_smoke(admin_token: str):
    """
    Smoke-check: добавить пользователя в tenant через POST, затем GET должен его вернуть.
    Требуется JWT пользователя с правами админа.
    """
    print("\n" + "=" * 60)
    print("TEST: Tenant users (POST add → GET list)")
    print("=" * 60)
    headers = {"Authorization": f"Bearer {admin_token}"}
    # Список tenants
    r = requests.get(f"{BASE_URL}/api/admin/tenants", headers=headers)
    if r.status_code != 200:
        print(f"[SKIP] Admin tenants: {r.status_code} (need admin)")
        return
    data = r.json()
    tenants = data.get("tenants") or []
    if not tenants:
        print("[SKIP] No tenants")
        return
    tenant_id = tenants[0]["id"]
    # Добавить пользователя по email (должен существовать в системе)
    email = "company2@test.kz"
    r = requests.post(
        f"{BASE_URL}/api/admin/tenants/{tenant_id}/users",
        headers=headers,
        json={"email": email, "role": "manager"},
    )
    if r.status_code not in (200, 201):
        print(f"[WARN] POST tenant user: {r.status_code} - {r.text}")
        return
    added = r.json()
    print(f"[OK] User added: {added.get('email')} role={added.get('role')}")
    # GET список пользователей tenant
    r = requests.get(f"{BASE_URL}/api/admin/tenants/{tenant_id}/users", headers=headers)
    if r.status_code != 200:
        print(f"[FAIL] GET tenant users: {r.status_code}")
        return
    list_data = r.json()
    users = list_data.get("users") or []
    found = [u for u in users if u.get("email") == email]
    if found:
        print(f"[OK] GET returned added user: {found[0]}")
    else:
        print("[FAIL] GET did not return added user")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("TESTIROVANIE AI SALES MANAGER SaaS API")
    print("=" * 60 + "\n")
    
    # 1. Авторизация
    token = test_auth_flow()
    
    if token:
        # 2. Чат
        test_chat_flow(token)
        
        # 3. Multi-tenancy
        test_multi_tenancy()

        # 4. Tenant users smoke (POST add → GET list; нужен admin)
        test_tenant_users_smoke(token)
    
    print("\n" + "=" * 60)
    print("TESTIROVANIE ZAVERSHENO!")
    print("=" * 60)
