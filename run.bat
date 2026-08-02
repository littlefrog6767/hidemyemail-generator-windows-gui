@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found in PATH. Install Python 3.10+ from python.org and try again.
  pause
  exit /b 1
)

if not exist ".venv\" (
  echo [INFO] Creating virtual environment and installing dependencies...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install --upgrade pip >nul
  pip install -r requirements.txt
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
  )
) else (
  call .venv\Scripts\activate.bat
)

python app.py
endlocal
