@echo off
setlocal

set "CONFIGURATION=Debug"
set "CONFIGURATION_DIR=debug"
if not "%~1"=="" (
  if /I "%~1"=="debug" (
    set "CONFIGURATION=Debug"
    set "CONFIGURATION_DIR=debug"
  ) else if /I "%~1"=="release" (
    set "CONFIGURATION=Release"
    set "CONFIGURATION_DIR=release"
  ) else (
    echo Usage: %~nx0 [debug^|release]
    echo.
    echo Builds both Android APK flavors from a clean Gradle state.
    echo Default: debug
    pause
    exit /b 1
  )
)

cd /d "%~dp0android-concept"
if errorlevel 1 (
  echo Failed to enter android-concept directory.
  pause
  exit /b 1
)

if not exist "gradlew.bat" (
  echo gradlew.bat was not found in %CD%.
  pause
  exit /b 1
)

where java >nul 2>nul
if errorlevel 1 (
  echo Java was not found. Install JDK 17, then run this launcher again.
  pause
  exit /b 1
)

echo Force-building Android %CONFIGURATION% APKs...
echo Project: %CD%
echo.

call gradlew.bat clean --rerun-tasks assembleGluco%CONFIGURATION% assembleFood%CONFIGURATION%
if errorlevel 1 (
  echo.
  echo Android APK build failed.
  pause
  exit /b 1
)

echo.
echo Android APK build complete.
echo.
echo Gluco APKs:
dir /b "app\build\outputs\apk\gluco\%CONFIGURATION_DIR%\*.apk"
echo.
echo Food APKs:
dir /b "app\build\outputs\apk\food\%CONFIGURATION_DIR%\*.apk"
pause
