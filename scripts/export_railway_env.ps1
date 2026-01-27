# ========================================
# Экспорт переменных окружения из Railway
# ========================================

Write-Host "🚂 Экспорт переменных из Railway..." -ForegroundColor Cyan

# Шаг 1: Установка Railway CLI (если не установлен)
Write-Host "`n📦 Проверка Railway CLI..." -ForegroundColor Yellow
try {
    railway --version | Out-Null
    Write-Host "✅ Railway CLI уже установлен" -ForegroundColor Green
} catch {
    Write-Host "⚠️  Railway CLI не найден. Установка..." -ForegroundColor Yellow
    npm install -g @railway/cli
}

# Шаг 2: Подключение к проекту
Write-Host "`n🔗 Подключение к Railway проекту..." -ForegroundColor Yellow
Write-Host "Если откроется браузер - подтвердите подключение" -ForegroundColor Gray
railway link

# Шаг 3: Экспорт переменных
Write-Host "`n📤 Экспорт переменных окружения..." -ForegroundColor Yellow
railway variables > .env.railway

Write-Host "`n✅ Переменные экспортированы в .env.railway" -ForegroundColor Green
Write-Host "📁 Файл: .env.railway" -ForegroundColor Cyan

# Шаг 4: Показать содержимое
Write-Host "`n📋 Содержимое:" -ForegroundColor Yellow
Get-Content .env.railway

Write-Host "`n💡 Чтобы использовать локально:" -ForegroundColor Cyan
Write-Host "   Скопируйте .env.railway в .env" -ForegroundColor Gray
Write-Host "   cp .env.railway .env" -ForegroundColor Gray
