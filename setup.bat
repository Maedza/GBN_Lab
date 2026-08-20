@echo off
setlocal enabledelayedexpansion
:: === GBN Lab — One-click Setup for Windows ===
:: Usage:  setup.bat         (just install)
::         setup.bat run     (install + launch the simulator)

echo =====================================
echo   GBN Lab — Setup
echo =====================================

:: ---- 1. Find Python 3 ----
set PYTHON=
for %%c in (python python3 py) do (
    where %%c >nul 2>&1
    if !errorlevel! equ 0 (
        set PYTHON=%%c
        goto :found
    )
)
:found
if "%PYTHON%"=="" (
    echo.
    echo ERROR: Python not found.
    echo   Install it from https://www.python.org/downloads/
    echo   ^(Make sure to check "Add Python to PATH" during installation^)
    pause
    exit /b 1
)
echo   Using: %PYTHON%
%PYTHON% --version

:: ---- 2. Create virtual environment (if missing) ----
if not exist "venv\" (
    echo   Creating virtual environment...
    %PYTHON% -m venv venv
)

:: ---- 3. Activate & install dependencies ----
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Failed to activate virtual environment.
    echo   If using PowerShell, run:
    echo     venv\Scripts\Activate.ps1
    echo     pip install -r requirements.txt
    pause
    exit /b 1
)

echo   Installing dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo.
echo   Done! All dependencies installed.
echo.

if /i "%~1"=="run" (
    echo   Launching GBN Lab...
    python app.py
) else (
    echo   To launch the simulator:
    echo.
    echo     venv\Scripts\activate
    echo     python app.py
    echo.
    echo   Or just:  setup.bat run
    pause
)
