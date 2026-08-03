@echo off
REM Build script for SpellCheck App with GUI (Windows)
setlocal enabledelayedexpansion

echo ========================================
echo SpellCheck App - Build Script
echo ========================================
echo.

REM Create virtual environment if it doesn't exist
if not exist ".venv" (
    echo Creating virtual environment...
    python -m venv .venv
    if !errorlevel! neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

REM Activate virtual environment
echo Activating virtual environment...
call .venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo ERROR: Failed to activate virtual environment.
    pause
    exit /b 1
)

echo Virtual environment active: %VIRTUAL_ENV%
echo.

REM Upgrade pip first
echo Upgrading pip... NO NO IT WAS REMd OUT
REM python -m pip install --upgrade pip >nul 2>&1

REM Install dependencies (trusted hosts for corporate firewalls)
echo Installing dependencies...
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo ERROR: Failed to install dependencies. Check your network/firewall settings.
    pause
    exit /b 1
)

REM Build standalone executable with GUI support
echo.
echo Building standalone executable...
pyinstaller --onefile ^
    --name "SpellCheck" ^
    --windowed ^
    --add-data "config.yaml;." ^
    main.py

if %errorlevel% equ 0 (
    copy /Y config.yaml dist\config.yaml >nul
    echo.
    echo ========================================
    echo Build successful!
    echo Executable location: dist\SpellCheck.exe
    echo GUI mode is the default. Use "--headless" only for background-only mode.
    echo Copy config.yaml to the same folder as SpellCheck.exe before first run.
    echo ========================================
) else (
    echo.
    echo ========================================
    echo ERROR: Build failed. Check errors above.
    echo ========================================
    pause
    exit /b 1
)

pause
