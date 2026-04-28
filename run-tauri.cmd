@echo off
setlocal

cd /d "%~dp0desktop"
if errorlevel 1 (
  echo Failed to enter desktop directory.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Install Node.js, then run this launcher again.
  pause
  exit /b 1
)

if not exist "node_modules" (
  echo Installing desktop dependencies...
  call npm install
  if errorlevel 1 (
    echo npm install failed.
    pause
    exit /b 1
  )
)

echo Closing any existing glucotracker desktop process...
taskkill /IM glucotracker-desktop.exe /F >nul 2>nul
taskkill /IM glucotracker.exe /F >nul 2>nul

echo Starting glucotracker desktop...
echo Backend should be running at http://127.0.0.1:8000.
call npm run tauri dev

if errorlevel 1 (
  echo Tauri failed to start.
  pause
  exit /b 1
)
