@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo   Publikater - Windows Installer ^& Launcher
echo ========================================================

:: Check for uv
where uv >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [INFO] 'uv' is not installed. Installing uv (fast Python package manager)...
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    
    :: Add uv to PATH for this session
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
    
    where uv >nul 2>nul
    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Failed to install 'uv' or add it to PATH.
        echo Please install uv manually from: https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
) else (
    echo [INFO] 'uv' is already installed.
)

:: Sync backend dependencies via uv
echo [INFO] Syncing backend dependencies...
cd backend
uv sync
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
cd ..

:: Launch the app using uv's managed python
echo [INFO] Launching Publikater...
uv run --project backend python launcher.py

pause
