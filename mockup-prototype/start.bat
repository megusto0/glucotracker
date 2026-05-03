@echo off
cd /d "%~dp0"

echo.
echo  glucotracker prototype
echo  ----------------------
echo.

where npm >/dev/null 2>nul
if errorlevel 1 (
    echo  ERROR: npm not found in PATH.
    echo  Install Node.js from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

if not exist node_modules (
    echo  Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo.
        echo  npm install failed.
        pause
        exit /b 1
    )
    echo.
)

echo  Starting dev server on http://127.0.0.1:5199 ...
echo  Press Ctrl+C to stop.
echo.
call npm run dev
if errorlevel 1 (
    echo.
    echo  Dev server exited with error.
    pause
)
