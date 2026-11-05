@echo off
setlocal enabledelayedexpansion

:: Force the script to run in its own directory (fixes zip extraction and run-as-admin issues)
cd /d "%~dp0"

echo ========================================================
echo   Publicat - Windows Installer ^& Launcher
echo ========================================================

:: Check for uv
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] First-time setup: Installing 'uv' (fast Python package manager)...
    
    :: Try installing uv. Group Policy might block this in strict corporate environments.
    powershell -ExecutionPolicy ByPass -Command "Invoke-RestMethod -Uri https://astral.sh/uv/install.ps1 | Invoke-Expression"
    
    :: Add uv to PATH for this session
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    
    where uv >nul 2>nul
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install 'uv' or corporate policy blocked the download.
        echo Please ask IT to install 'uv' or run this manually:
        echo curl -LsSf https://astral.sh/uv/install.ps1 ^^| powershell -c -
        pause
        exit /b 1
    )
) else (
    echo [INFO] 'uv' is already installed.
)

:: Sync backend dependencies via uv
echo [INFO] Syncing backend dependencies...
cd backend

:: uv sync will automatically download Python if it's not installed!
uv sync --extra local
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)
cd ..

:: Launch the app using uv's managed python
echo [INFO] Launching Publicat...
uv run --project backend python launcher.py %*

:: Only pause if it crashes, otherwise let it close smoothly
if %ERRORLEVEL% neq 0 pause
