@echo off
echo ========================================
echo   UNIFIED CONFIG SYNC - .env PROPAGATOR
echo ========================================

set ROOT_ENV=config\.env

if not exist %ROOT_ENV% (
    echo [ERROR] Root .env file not found at %ROOT_ENV%
    exit /b 1
)

echo [INFO] Syncing configuration to apps...

:: Historical Dashboard
echo NEXT_PUBLIC_API_BASE=http://localhost:8080 > apps\historical_dashboard\.env.local
echo NEXT_PUBLIC_WS_BASE=ws://localhost:8765 >> apps\historical_dashboard\.env.local
type %ROOT_ENV% >> apps\historical_dashboard\.env.local
echo [SUCCESS] Synced to apps\historical_dashboard\.env.local

:: Forge Dashboard
echo NEXT_PUBLIC_API_BASE=http://localhost:8081 > apps\forge_dashboard\.env.local
type %ROOT_ENV% >> apps\forge_dashboard\.env.local
echo [SUCCESS] Synced to apps\forge_dashboard\.env.local

:: Trading Core (Python already looks at config/.env, but we can copy for local service development if needed)
:: For now, core config logic in trading_core/config/__init__.py is already correct.

echo.
echo Configuration sync complete.
