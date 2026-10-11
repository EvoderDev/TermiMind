@echo off
setlocal EnableDelayedExpansion

echo =====================================================================
echo  TermiMind: CLI Copilot ^& Error Healer - Setup (Windows)
echo =====================================================================

:: 1. Check Python installation
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python is not installed or not in your system PATH.
    echo Please install Python 3.9 or higher from https://www.python.org/
    exit /b 1
)

:: 2. Check Python version (requires >= 3.9)
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.9 or higher is required.
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo Current version: %%v
    exit /b 1
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo [OK] Detected %%v

:: 3. Create virtual environment (.venv) if it does not exist
if not exist ".venv\Scripts\activate.bat" (
    echo [*] Creating virtual environment in .venv ...
    python -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        exit /b 1
    )
    echo [OK] Virtual environment created successfully.
) else (
    echo [OK] Existing virtual environment found in .venv.
)

:: 4. Activate virtual environment
echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    exit /b 1
)

:: 5. Upgrade pip
echo [*] Upgrading pip...
python -m pip install --upgrade pip --quiet

:: 6. Install requirements
echo [*] Installing dependencies from requirements.txt...
pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    exit /b 1
)

:: 7. Install package in editable mode
echo [*] Installing TermiMind in editable development mode (pip install -e .)...
pip install -e .
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install TermiMind package.
    exit /b 1
)

:: 8. Verify installation
echo [*] Verifying installation...
termimind --version
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Direct command 'termimind' test failed, testing module entrypoint...
    python -m termimind --version
)

echo =====================================================================
echo  [SUCCESS] TermiMind setup completed successfully!
echo =====================================================================
echo To start using TermiMind:
echo   1. Activate virtual environment: .venv\Scripts\activate
echo   2. Run TermiMind:                termimind fix  (or 'tm')
echo   3. Start background listener:    termimind listen
echo   4. Set up shell hook:            termimind hook powershell
echo =====================================================================
