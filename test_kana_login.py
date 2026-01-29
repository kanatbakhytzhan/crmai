"""
Тест авторизации для аккаунта Kana (skai.media)
"""
import requests

BASE_URL = "http://localhost:8000"


def test_kana_login():
    """Тест авторизации и получения токена"""
    
    print("=" * 70)
    print("TEST: KANA LOGIN (skai.media)")
    print("=" * 70)
    
    # Шаг 1: Логин
    print("\n[1/3] Login...")
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": "kana.bahytzhan@gmail.com",
            "password": "Kanaezz15!"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data["access_token"]
        print(f"    [OK] Login successful!")
        print(f"    Token: {token[:50]}...")
    else:
        print(f"    [ERROR] Login failed: {response.status_code}")
        print(f"    {response.text}")
        return
    
    # Шаг 2: Получить информацию о профиле
    print("\n[2/3] Get profile info...")
    
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        profile = response.json()
        print(f"    [OK] Profile loaded!")
        print(f"    ID: {profile['id']}")
        print(f"    Email: {profile['email']}")
        print(f"    Company: {profile['company_name']}")
    else:
        print(f"    [ERROR] Profile failed: {response.status_code}")
    
    # Шаг 3: Получить заявки
    print("\n[3/3] Get leads...")
    
    response = requests.get(
        f"{BASE_URL}/api/leads",
        headers={"Authorization": f"Bearer {token}"}
    )
    
    if response.status_code == 200:
        data = response.json()
        leads = data if isinstance(data, list) else []
        print(f"    [OK] Leads loaded!")
        print(f"    Total leads: {len(leads)}")
        
        if leads:
            print(f"\n    Recent leads:")
            for lead in leads[:5]:
                status = lead.get('status', 'N/A')
                print(f"      - [{lead['id']}] {lead['name']} ({lead['phone']}) - {status}")
        else:
            print(f"    (No leads yet - try the web chat!)")
    else:
        print(f"    [ERROR] Leads failed: {response.status_code}")
    
    # Итог
    print("\n" + "=" * 70)
    print("SUCCESS!")
    print("=" * 70)
    print(f"\nYour JWT Token:")
    print(f"{token}")
    
    print(f"\n[HOW TO USE]")
    print(f"\n1. Admin Panel:")
    print(f"   http://localhost:8000/admin")
    print(f"   Login: admin / admin123")
    
    print(f"\n2. Web Chat (for clients):")
    print(f"   http://192.168.0.10:8000/")
    print(f"   Try: Click microphone, say 'Хочу дом'")
    
    print(f"\n3. API (for mobile app):")
    print(f"   Authorization: Bearer {token}")
    print(f"   GET /api/leads - Your leads")
    print(f"   PATCH /api/leads/{{id}} - Update status")
    
    print(f"\n4. All web chat leads -> skai.media (owner_id=1)")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        test_kana_login()
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Server is not running!")
        print("Start it: python main.py")
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
