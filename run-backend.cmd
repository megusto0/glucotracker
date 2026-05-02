@echo off
setlocal

cd /d "%~dp0backend"
if errorlevel 1 (
  echo Failed to enter backend directory.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3.11 or newer, then run this launcher again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating backend virtual environment...
  python -m venv .venv
  if errorlevel 1 (
    echo Failed to create virtual environment.
    pause
    exit /b 1
  )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Failed to activate backend virtual environment.
  pause
  exit /b 1
)

if not exist "glucotracker_backend.egg-info" (
  echo Installing backend dependencies...
  python -m pip install --upgrade pip
  python -m pip install -e .
  if errorlevel 1 (
    echo Backend dependency install failed.
    pause
    exit /b 1
  )
)

if "%GLUCOTRACKER_TOKEN%"=="" (
  set "GLUCOTRACKER_TOKEN=dev"
)

echo Applying database migrations...
alembic upgrade head
if errorlevel 1 (
  echo Alembic migration failed.
  pause
  exit /b 1
)

echo Starting glucotracker backend...
echo API: http://0.0.0.0:8000
echo Token: %GLUCOTRACKER_TOKEN%
python -m uvicorn glucotracker.main:app --reload --host 0.0.0.0 --port 8000

if errorlevel 1 (
  echo Backend failed to start.
  pause
  exit /b 1
)

