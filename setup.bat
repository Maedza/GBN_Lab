@echo off
echo === GBN Lab Setup ===

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install it from https://python.org
    pause
    exit /b 1
)

echo Using:
python --version

if not exist "venv\" (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate
echo Installing dependencies...
pip install --quiet -r requirements.txt

echo.
echo Done. To run the simulator:
echo   venv\Scripts\activate  ^(if not already active^)
echo   python main.py
pause
