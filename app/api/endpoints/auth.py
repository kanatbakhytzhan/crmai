"""
API эндпоинты для авторизации
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.database import crud
from app.database.models import User
from app.schemas import UserCreate, UserResponse, Token
from app.core.security import verify_password, create_access_token

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Регистрация нового пользователя (компании)
    
    Args:
        user_data: Email, Password, CompanyName
        
    Returns:
        Данные созданного пользователя
        
    Raises:
        400: Email уже используется
    """
    # Проверяем не занят ли email
    existing_user = await crud.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Создаем пользователя
    user = await crud.create_user(
        db=db,
        email=user_data.email,
        password=user_data.password,
        company_name=user_data.company_name
    )
    
    return user


@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Авторизация пользователя (получение JWT токена)
    
    Args:
        form_data: OAuth2 форма (username=email, password)
        
    Returns:
        JWT токен
        
    Raises:
        401: Неверный email или пароль
    """
    # Ищем пользователя по email (username в OAuth2PasswordRequestForm)
    user = await crud.get_user_by_email(db, form_data.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем пароль
    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Проверяем активен ли аккаунт
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled"
        )
    
    # Создаем JWT токен
    access_token = create_access_token(data={"sub": user.email})
    
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """
    Получить информацию о текущем авторизованном пользователе
    
    Требует JWT токен в заголовке Authorization: Bearer <token>
    """
    return current_user
