@echo off
REM Start both backend and frontend in separate windows
start "ai-backend" cmd /c "%~dp0start_backend.bat"
ping -n 3 127.0.0.1 >nul
start "ai-frontend" cmd /c "%~dp0start_frontend.bat"
echo [OK] Services launched in new windows:
echo   Backend : http://127.0.0.1:8000  (API docs at /docs)
echo   Frontend: http://localhost:5173
REM Open browser after frontend is ready (delayed in background)
start "" cmd /c "ping -n 9 127.0.0.1 >nul & start http://localhost:5173"
