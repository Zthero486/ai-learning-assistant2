@echo off
REM 一键启动：后端 + 前端 各开一个窗口
start "AI学习助手-后端" cmd /c "%~dp0start_backend.bat"
timeout /t 2 >nul
start "AI学习助手-前端" cmd /c "%~dp0start_frontend.bat"
echo 两个服务已在新窗口启动：
echo   后端  http://127.0.0.1:8000  （接口文档 /docs）
echo   前端  http://localhost:5173
