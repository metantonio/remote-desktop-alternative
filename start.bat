@echo off
setlocal
title Desk - Remote Desktop

:: Check if virtual environment exists
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL% equ 0 (
        set "PYTHON_EXE=python"
    ) else (
        echo [ERROR] Python was not found!
        echo Please make sure Python or the .venv virtual environment is installed.
        pause
        exit /b 1
    )
)

:: Run the Desk Graphical Interface
echo Starting Desk Remote Desktop Interface...
"%PYTHON_EXE%" -m desk gui %*

if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Desk exited with an error.
    pause
)
