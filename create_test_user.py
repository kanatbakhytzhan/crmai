"""
Скрипт для создания тестового пользователя
"""
import asyncio
from app.database.session import AsyncSessionLocal
from app.database import crud


async def create_test_user():
    """Создать тестового пользователя"""
    async with AsyncSessionLocal() as db:
        # Проверяем существует ли пользователь
        existing = await crud.get_user_by_email(db, "test@company.kz")
        
        if existing:
            print(f"[OK] Polzovatel uzhe sushchestvuet:")
            print(f"    Email: {existing.email}")
            print(f"    Company: {existing.company_name}")
            print(f"    ID: {existing.id}")
        else:
            # Создаем нового пользователя
            user = await crud.create_user(
                db=db,
                email="test@company.kz",
                password="test123",
                company_name="Тестовая Компания"
            )
            print(f"[OK] Polzovatel sozdan:")
            print(f"    Email: {user.email}")
            print(f"    Company: {user.company_name}")
            print(f"    ID: {user.id}")
        
        print("\n[INFO] Dlya logina ispolzuite:")
        print(f"    Email: test@company.kz")
        print(f"    Password: test123")


if __name__ == "__main__":
    print("[*] Sozdanie testovogo polzovatelya...\n")
    asyncio.run(create_test_user())
