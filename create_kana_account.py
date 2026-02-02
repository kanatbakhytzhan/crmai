"""
Создание/обновление админ-аккаунта Kana (skai.media).
Создаёт пользователя kana.bahytzhan@gmail.com с паролем Kanaezz15! и is_admin=True.
Если пользователь уже есть — ставит is_admin=True и при необходимости обновляет пароль.
"""
import asyncio

from app.database.session import AsyncSessionLocal, init_db
from app.database import crud

EMAIL = "kana.bahytzhan@gmail.com"
PASSWORD = "Kanaezz15!"
COMPANY = "skai.media"


async def create_kana_account():
    """Создать или обновить админ-аккаунт Kana."""
    await init_db()

    print("=" * 70)
    print("KANA ADMIN ACCOUNT (skai.media)")
    print("=" * 70)

    async with AsyncSessionLocal() as db:
        existing = await crud.get_user_by_email(db, EMAIL)

        if existing:
            # Обновляем: is_admin=True и пароль (на случай смены)
            await crud.set_user_password(db, existing.id, PASSWORD)
            user = await crud.update_user(db, existing.id, is_admin=True)
            user = user or existing
            print(f"\n[OK] User already exists, updated to admin + password reset.")
            print(f"     ID: {user.id}, Email: {user.email}, is_admin: {getattr(user, 'is_admin', True)}")
        else:
            user = await crud.create_user(
                db=db,
                email=EMAIL,
                password=PASSWORD,
                company_name=COMPANY,
            )
            user = await crud.update_user(db, user.id, is_admin=True) or user
            print(f"\n[OK] New admin user created.")
            print(f"     ID: {user.id}, Email: {user.email}")

        print(f"\n[LOGIN]")
        print(f"   Email:    {EMAIL}")
        print(f"   Password: {PASSWORD}")
        print(f"\n   POST /api/auth/login  (username=email, password=password)")
        print(f"   Then use JWT in Authorization: Bearer <token> for /api/admin/* and /api/leads")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_kana_account())
