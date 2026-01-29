# PowerShell скрипт для запуска приложения

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI SALES MANAGER - Запуск сервера" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Проверка виртуального окружения
if (Test-Path "venv\Scripts\Activate.ps1") {
    Write-Host "Активация виртуального окружения..." -ForegroundColor Green
    & .\venv\Scripts\Activate.ps1
} else {
    Write-Host "[ОШИБКА] Виртуальное окружение не найдено!" -ForegroundColor Red
    Write-Host "Создайте его командой: python -m venv venv" -ForegroundColor Yellow
    pause
    exit 1
}

# Запуск приложения
Write-Host "Запуск сервера..." -ForegroundColor Green
python main.py
