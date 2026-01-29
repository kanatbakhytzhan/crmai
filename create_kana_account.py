"""
Создание аккаунта для Kana (skai.media)
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.database import crud
from app.schemas.user import UserCreate


async def create_kana_account():
    """Создание аккаунта Kana с ID=1"""
    
    print("=" * 70)
    print("CREATING KANA ACCOUNT (skai.media)")
    print("=" * 70)
    
    async with AsyncSessionLocal() as db:
        # Проверяем существует ли пользователь
        existing = await crud.get_user_by_email(db, "kana.bahytzhan@gmail.com")
        
        if existing:
            print(f"\n[INFO] User already exists!")
            print(f"       ID: {existing.id}")
            print(f"       Email: {existing.email}")
            print(f"       Company: {existing.company_name}")
            print(f"\n[INFO] Use this for login:")
            print(f"       Email: kana.bahytzhan@gmail.com")
            print(f"       Password: Kanaezz15!")
            return
        
        # Создаем нового пользователя
        user = await crud.create_user(
            db=db,
            email="kana.bahytzhan@gmail.com",
            password="Kanaezz15!",
            company_name="skai.media"
        )
        
        print(f"\n[SUCCESS] Account created!")
        print(f"\n" + "=" * 70)
        print(f"  SKAI.MEDIA - Account Details")
        print(f"=" * 70)
        print(f"  ID:       {user.id}")
        print(f"  Email:    {user.email}")
        print(f"  Company:  {user.company_name}")
        print(f"  Active:   {user.is_active}")
        print(f"=" * 70)
        
        print(f"\n[LOGIN CREDENTIALS]")
        print(f"   Email:    kana.bahytzhan@gmail.com")
        print(f"   Password: Kanaezz15!")
        
        print(f"\n[ACCESS POINTS]")
        print(f"   Admin Panel:  http://localhost:8000/admin")
        print(f"                 (admin / admin123)")
        print(f"\n   Web Chat:     http://192.168.0.10:8000/")
        print(f"                 (For clients)")
        
        print(f"\n   API (Swagger): http://localhost:8000/docs")
        print(f"                  (Use login endpoint to get JWT token)")
        
        print(f"\n[NEXT STEPS]")
        print(f"   1. Login to get JWT token:")
        print(f"      POST /api/auth/login")
        print(f"      username: kana.bahytzhan@gmail.com")
        print(f"      password: Kanaezz15!")
        
        print(f"\n   2. Use token to access your leads:")
        print(f"      GET /api/leads")
        print(f"      Authorization: Bearer YOUR_TOKEN")
        
        print(f"\n   3. All leads from web chat will be assigned to you!")
        print(f"      (owner_id = {user.id})")
        
        print(f"\n" + "=" * 70)
        print("READY TO USE! 🚀")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_kana_account())
