@echo off
set PYTHONPATH=%CD%
echo =========================================
echo 1. Running Flake8 (Static Code Analysis)
echo =========================================
echo Checking for critical errors (Syntax, undefined variables)...
call venv\Scripts\flake8.exe --select=E9,F63,F7,F82 ui\main_window.py sync_worker.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Flake8 found CRITICAL issues! Please fix them before building.
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] Code syntax looks good!
echo.

echo =========================================
echo 2. Running Pytest (Automated UI Test)
echo =========================================
call venv\Scripts\pytest.exe tests\ -v

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Tests failed! The app might crash or have bugs.
    pause
    exit /b %ERRORLEVEL%
)
echo [OK] All tests passed! The app works successfully.
echo.
pause
