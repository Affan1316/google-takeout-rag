@echo off
REM Start the CSV Processor API on Windows

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║     CSV Data Processor API - FastAPI Server            ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Check if app.py exists
if not exist app.py (
    echo ERROR: app.py not found in current directory!
    echo Please navigate to the correct directory.
    pause
    exit /b 1
)

REM Install dependencies if requirements.txt exists
if exist requirements.txt (
    echo Installing dependencies...
    pip install -r requirements.txt
    echo.
)

REM Start the server
echo Starting FastAPI server...
echo.
echo ✓ API will be available at: http://localhost:8000
echo ✓ Swagger UI: http://localhost:8000/docs
echo ✓ ReDoc: http://localhost:8000/redoc
echo ✓ Health Check: http://localhost:8000/status
echo.
echo Press Ctrl+C to stop the server.
echo.

python app.py

pause
