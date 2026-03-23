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

REM --------------- bootstrap tesseract ---------------
set "TESSERACT_EXE="
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESSERACT_EXE=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
if not defined TESSERACT_EXE if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESSERACT_EXE=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"
if not defined TESSERACT_EXE for /f "delims=" %%I in ('where tesseract.exe 2^>nul') do if not defined TESSERACT_EXE set "TESSERACT_EXE=%%~fI"

if not defined TESSERACT_EXE (
    where winget >nul 2>nul
    if errorlevel 1 (
        echo [error] Tesseract OCR is missing and winget is not available.
        echo [error] Install App Installer or install Tesseract manually, then retry.
        pause
        exit /b 1
    )
    echo [setup] Tesseract OCR was not found. Installing it now...
    winget install -e --id UB-Mannheim.TesseractOCR --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [error] Tesseract OCR install failed.
        pause
        exit /b 1
    )
    if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" set "TESSERACT_EXE=%ProgramFiles%\Tesseract-OCR\tesseract.exe"
    if not defined TESSERACT_EXE if exist "%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe" set "TESSERACT_EXE=%LocalAppData%\Programs\Tesseract-OCR\tesseract.exe"
    if not defined TESSERACT_EXE for /f "delims=" %%I in ('where tesseract.exe 2^>nul') do if not defined TESSERACT_EXE set "TESSERACT_EXE=%%~fI"
)

if not defined TESSERACT_EXE (
    echo [error] Tesseract OCR is still unavailable after installation.
    pause
    exit /b 1
)

for %%I in ("%TESSERACT_EXE%") do set "TESSERACT_DIR=%%~dpI"
set "PATH=%TESSERACT_DIR%;%PATH%"
set "TESSDATA_DIR=%TESSERACT_DIR%tessdata"
if defined TESSDATA_PREFIX if exist "%TESSDATA_PREFIX%\chi_sim.traineddata" set "TESSDATA_DIR=%TESSDATA_PREFIX%"
if not exist "%TESSDATA_DIR%" mkdir "%TESSDATA_DIR%"
if not exist "%TESSDATA_DIR%\chi_sim.traineddata" (
    echo [setup] Chinese OCR data was not found. Downloading it now...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://github.com/tesseract-ocr/tessdata_fast/raw/main/chi_sim.traineddata' -OutFile '%TESSDATA_DIR%\chi_sim.traineddata'"
    if errorlevel 1 (
        echo [error] Failed to download chi_sim.traineddata.
        pause
        exit /b 1
    )
)
set "TESSDATA_PREFIX=%TESSDATA_DIR%"

REM --------------- sync environment ---------------
uv sync --no-editable --extra tesseract
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
