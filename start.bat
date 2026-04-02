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

REM --------------- sync environment ---------------
set "UV_CACHE_DIR=%CD%\.uv-cache"
set "UV_LINK_MODE=copy"
if not exist "%UV_CACHE_DIR%" mkdir "%UV_CACHE_DIR%"
call :sync_env
if errorlevel 1 (
    echo [error] Failed to prepare the runtime environment.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [error] Python executable was not created in .venv.
    pause
    exit /b 1
)
set "PYTHONPATH=%CD%\src"

REM --------------- auto-open browser ---------------
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://%HOST%:%PORT%"

echo [start] Web UI is starting at http://%HOST%:%PORT%
echo [start] Your browser will open automatically.
echo [start] Close this window to stop the service.
echo.

REM --------------- launch ---------------
REM The environment is ready, so launch the module from the project virtualenv.
".venv\Scripts\python.exe" -m wukong_invite.webui --host %HOST% --port %PORT%

pause
exit /b 0

:sync_env
uv sync --link-mode copy --cache-dir "%UV_CACHE_DIR%" --no-editable --no-install-project
if not errorlevel 1 exit /b 0
echo [warn] First dependency sync failed. Retrying once...
timeout /t 2 /nobreak >nul
uv sync --link-mode copy --cache-dir "%UV_CACHE_DIR%" --no-editable --no-install-project
exit /b %errorlevel%
