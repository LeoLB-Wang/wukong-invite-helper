@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

cd /d "%~dp0"

set "PORT=8787"
set "HOST=127.0.0.1"

echo.
echo   ==========================================
echo        悟空邀请码助手 · 一键启动
echo   ==========================================
echo.

:: --------------- auto-install uv ---------------
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo [setup] 未检测到 uv，正在自动安装...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    where uv >nul 2>&1
    if !errorlevel! neq 0 (
        echo [error] uv 安装失败，请手动安装: https://docs.astral.sh/uv/
        pause
        exit /b 1
    )
    echo [setup] uv 安装完成
)

echo [setup] 正在准备运行环境（首次启动需下载依赖，请稍候）...

:: --------------- auto-open browser ---------------
start "" cmd /c "timeout /t 3 /nobreak >nul && start http://%HOST%:%PORT%"

echo [start] Web UI 启动中 - http://%HOST%:%PORT%
echo [start] 浏览器将自动打开，关闭此窗口即可停止服务
echo.

:: --------------- launch ---------------
:: uv run 自动完成: 安装 Python - 创建 .venv - 安装依赖 - 运行
uv run wukong-invite-webui --host %HOST% --port %PORT%

pause
