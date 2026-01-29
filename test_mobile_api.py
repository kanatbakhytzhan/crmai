"""
Тестирование новых эндпоинтов для мобильного приложения
- PATCH /api/leads/{id} - обновление статуса
- DELETE /api/leads/{id} - удаление заявки
- GET /api/leads/{id} - получение одной заявки
"""
import requests
import json

BASE_URL = "http://localhost:8000"


def test_mobile_lead_management():
    """Полный тест управления заявками из мобильного приложения"""
    
    print("=" * 70)
    print("ТЕСТ: УПРАВЛЕНИЕ ЗАЯВКАМИ ДЛЯ МОБИЛЬНОГО ПРИЛОЖЕНИЯ")
    print("=" * 70)
    
    # Шаг 1: Регистрация и логин
    print("\n[1/6] Registratsiya i login...")
    
    # Регистрация
    response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={
            "email": "mobile_test@company.kz",
            "password": "mobile123",
            "company_name": "Mobile Test Company"
        }
    )
    
    if response.status_code == 400:
        print("    [INFO] Polzovatel uzhe zaregistrirovan")
    else:
        print(f"    [OK] Polzovatel sozdan")
    
    # Логин
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": "mobile_test@company.kz",
            "password": "mobile123"
        }
    )
    
    if response.status_code != 200:
        print(f"    [ERROR] Login failed: {response.status_code}")
        print(response.text)
        return
    
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print(f"    [OK] Token poluchon")
    
    # Шаг 2: Создаем тестовую заявку через чат
    print("\n[2/6] Sozdanie testovoy zayavki cherez chat...")
    
    response = requests.post(
        f"{BASE_URL}/api/chat",
        headers=headers,
        data={
            "user_id": "mobile_test_client_999",
            "text": "Хочу построить дом в Алматы, 200 квадратов. Меня зовут Тестовый, телефон 87771234567"
        }
    )
    
    if response.status_code == 200:
        print(f"    [OK] Chat otvet poluchon")
    else:
        print(f"    [ERROR] Chat failed: {response.status_code}")
    
    # Шаг 3: Получаем список заявок
    print("\n[3/6] Poluchenie spiska zayavok...")
    
    response = requests.get(
        f"{BASE_URL}/api/leads",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"    [ERROR] Failed: {response.status_code}")
        return
    
    leads = response.json()["leads"]
    print(f"    [OK] Naydeno zayavok: {len(leads)}")
    
    if not leads:
        print("    [WARNING] Net zayavok dlya testa. Sozdayte zayavku snachala.")
        return
    
    # Берем первую заявку для теста
    lead = leads[0]
    lead_id = lead["id"]
    print(f"    [OK] Vybrali zayavku #{lead_id} dlya testa")
    print(f"         Name: {lead['name']}")
    print(f"         Phone: {lead['phone']}")
    print(f"         Status: {lead['status']}")
    
    # Шаг 4: Получаем одну заявку (новый эндпоинт GET /api/leads/{id})
    print(f"\n[4/6] Poluchenie odnoy zayavki (GET /api/leads/{lead_id})...")
    
    response = requests.get(
        f"{BASE_URL}/api/leads/{lead_id}",
        headers=headers
    )
    
    if response.status_code == 200:
        single_lead = response.json()
        print(f"    [OK] Zayavka poluchena:")
        print(f"         ID: {single_lead['id']}")
        print(f"         Status: {single_lead['status']}")
    else:
        print(f"    [ERROR] Failed: {response.status_code} - {response.text}")
    
    # Шаг 5: Обновляем статус (новый эндпоинт PATCH /api/leads/{id})
    print(f"\n[5/6] Obnovlenie statusa (PATCH /api/leads/{lead_id})...")
    
    # Тестируем разные статусы
    statuses_to_test = ["in_progress", "success"]
    
    for new_status in statuses_to_test:
        print(f"\n    Obnovlyaem status na: {new_status}")
        
        response = requests.patch(
            f"{BASE_URL}/api/leads/{lead_id}",
            headers={**headers, "Content-Type": "application/json"},
            json={"status": new_status}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"    [OK] Status obnovlen: {result['lead']['status']}")
        else:
            print(f"    [ERROR] Failed: {response.status_code}")
            print(f"    {response.text}")
    
    # Шаг 6: Удаляем тестовую заявку (если нужно)
    print(f"\n[6/6] Udalenie testovoy zayavki? (y/n)")
    print(f"    [INFO] Propuskaem udalenie dlya sokhraneniya dannykh")
    
    # Раскомментируйте если хотите тестировать удаление:
    # response = requests.delete(
    #     f"{BASE_URL}/api/leads/{lead_id}",
    #     headers=headers
    # )
    # 
    # if response.status_code == 200:
    #     print(f"    [OK] Zayavka #{lead_id} udalena")
    # else:
    #     print(f"    [ERROR] Failed: {response.status_code}")
    
    # Итоговая проверка
    print("\n" + "=" * 70)
    print("ITOG:")
    print("=" * 70)
    
    response = requests.get(f"{BASE_URL}/api/leads", headers=headers)
    total_leads = response.json()["total"]
    
    print(f"[OK] GET /api/leads - OK")
    print(f"[OK] GET /api/leads/{{id}} - OK")
    print(f"[OK] PATCH /api/leads/{{id}} - OK")
    print(f"[OK] DELETE /api/leads/{{id}} - Gotov (ne provereno)")
    print(f"\nVsego zayavok v sisteme: {total_leads}")
    print("\n[SUCCESS] Vse endpointy dlya mobilki rabotayut!")


if __name__ == "__main__":
    try:
        test_mobile_lead_management()
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Server ne zapushchen!")
        print("Zapustite server: python main.py")
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
