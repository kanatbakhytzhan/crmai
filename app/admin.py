"""
Админ-панель для управления данными (SQLAdmin)
ИСПРАВЛЕНА ВЕРСИЯ - совместимость с AsyncEngine
"""
import logging
from sqladmin import Admin, ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.database.models import User, BotUser, Lead
from app.core.config import get_settings


# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


class AdminAuth(AuthenticationBackend):
    """
    Аутентификация для админ-панели (/admin).
    Логин из ENV: ADMIN_PANEL_USERNAME, ADMIN_PANEL_PASSWORD (по умолчанию admin / admin123).
    """
    
    async def login(self, request: Request) -> bool:
        import os
        form = await request.form()
        username = (form.get("username") or "").strip()
        password = (form.get("password") or "").strip()
        
        admin_username = (os.getenv("ADMIN_PANEL_USERNAME") or "admin").strip()
        admin_password = (os.getenv("ADMIN_PANEL_PASSWORD") or "admin123").strip()
        
        if username == admin_username and password == admin_password:
            request.session.update({"admin": "authenticated"})
            return True
        
        return False
    
    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
    
    async def authenticate(self, request: Request) -> bool:
        return request.session.get("admin") == "authenticated"


class UserAdmin(ModelView, model=User):
    """
    Компании (владельцы)
    """
    name = "Компания"
    name_plural = "Компании"
    icon = "fa-solid fa-building"
    
    column_list = [User.id, User.email, User.company_name]
    
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = False  # ОТКЛЮЧЕНО
    
    # ОТКЛЮЧЕНО: поиск
    # column_searchable_list = []


class BotUserAdmin(ModelView, model=BotUser):
    """
    Клиенты бота
    """
    name = "Клиент"
    name_plural = "Клиенты"
    icon = "fa-solid fa-user"
    
    column_list = [BotUser.id, BotUser.name, BotUser.phone]
    
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = False  # ОТКЛЮЧЕНО
    
    # ОТКЛЮЧЕНО: поиск
    # column_searchable_list = []


class LeadAdmin(ModelView, model=Lead):
    """
    Заявки (основной функционал)
    
    МАКСИМАЛЬНО УПРОЩЕНО ДЛЯ СОВМЕСТИМОСТИ С ASYNCENGINE
    """
    name = "Заявка"
    name_plural = "Заявки"
    icon = "fa-solid fa-clipboard-list"
    
    # ТОЛЬКО базовые String поля
    column_list = [Lead.id, Lead.name, Lead.phone, Lead.city]
    
    # МИНИМУМ редактирования
    form_columns = [Lead.name, Lead.phone, Lead.city]
    
    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = False  # ОТКЛЮЧЕНО
    
    # ОТКЛЮЧЕНО: поиск может вызывать проблемы
    # column_searchable_list = []


def setup_admin(app, engine):
    """
    Настройка админ-панели для AsyncEngine
    """
    try:
        secret_key = settings.secret_key
        
        logger.info("=" * 70)
        logger.info("ADMIN PANEL INITIALIZATION")
        logger.info("=" * 70)
        logger.info(f"Engine type: {type(engine).__name__}")
        logger.info(f"Engine URL: {engine.url}")
        logger.info(f"SQLAdmin version: compatible with AsyncEngine")
        
        # Создаем админ-панель
        admin = Admin(
            app=app,
            engine=engine,
            title="AI Sales Manager - Admin",
            base_url="/admin",
            authentication_backend=AdminAuth(secret_key=secret_key),
        )
        
        # Регистрируем модели
        logger.info("Registering models...")
        admin.add_view(LeadAdmin)
        admin.add_view(BotUserAdmin)
        admin.add_view(UserAdmin)
        
        logger.info("[OK] Admin panel initialized successfully!")
        logger.info("=" * 70)
        print("\n[OK] Admin panel: http://localhost:8000/admin")
        print("     Login: admin / admin123\n")
        
        return admin
        
    except Exception as e:
        logger.error(f"FAILED to initialize admin: {e}", exc_info=True)
        raise
