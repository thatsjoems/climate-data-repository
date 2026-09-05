@echo off
REM Climate Data Repository - one-click startup (Windows)
REM Double-click this file to start both Backend and Frontend automatically.

echo Starting CDR Backend...
start "CDR Backend" cmd /k "cd backend && venv\Scripts\activate && python -m uvicorn app.main:app --reload"

echo Waiting for backend to initialize...
timeout /t 4 /nobreak >nul

echo Starting CDR Frontend...
start "CDR Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo Both services are starting in separate windows.
echo Once ready, open: http://localhost:5173
echo.
pause
