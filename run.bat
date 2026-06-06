@echo off
setlocal

:: Navigate to the directory containing this batch file
cd /d "%~dp0"

:: 1. Check if virtual environment exists; if not, create it and install requirements
if not exist ".venv" (
    echo [setup] Creating local Python virtual environment (.venv)...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] Failed to create virtual environment. Make sure Python is installed and in your PATH.
        pause
        exit /b 1
    )
    
    echo [setup] Activating environment and installing dependencies...
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip
    pip install -r back-end/requirements.txt
) else (
    echo [setup] Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: 3. Launch the backend API server in the current CMD window
echo [setup] Starting Python API Server on http://localhost:8089...
echo.
echo ===================================================================
echo   BVB Portfolio Dashboard is running!
echo   Open your browser and go to: http://localhost:8089/dashboard.html
echo ===================================================================
echo.
echo [log] Backend API logs will print below. Press Ctrl+C to stop.
echo.

python back-end/server.py

endlocal
