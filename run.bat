@echo off
echo ========================================
echo   AI SALES MANAGER - Запуск сервера
echo ========================================
echo.

REM Активация виртуального окружения
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
) else (
    echo [ОШИБКА] Виртуальное окружение не найдено!
    echo Создайте его командой: python -m venv venv
    pause
    exit /b 1
)

REM Запуск приложения
echo Запуск сервера...
python main.py

pause
