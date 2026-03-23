@echo off
setlocal

cd /d "%~dp0"

set "PORT=8787"
set "HOST=127.0.0.1"

echo.
echo   ==========================================
echo        Wukong Invite Helper Launcher
echo   ==========================================
echo.

REM --------------- auto-install uv ---------------
where uv >nul 2>nul
if errorlevel 1 (
    echo [setup] uv was not found. Installing it now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>nul
    if errorlevel 1 (
        echo [error] uv install failed. Please install it manually:
        echo         https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    echo [setup] uv installation finished.
)

echo [setup] Preparing runtime environment. First launch may take a minute...

REM --------------- auto-open browser ---------------
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://%HOST%:%PORT%"

echo [start] Web UI is starting at http://%HOST%:%PORT%
echo [start] Your browser will open automatically.
echo [start] Close this window to stop the service.
echo.

REM --------------- launch ---------------
REM uv run will install Python, create .venv, install deps, and launch the app.
uv run wukong-invite-webui --host %HOST% --port %PORT%

pause
