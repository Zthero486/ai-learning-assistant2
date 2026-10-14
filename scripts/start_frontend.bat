@echo off
REM 一键启动前端开发服务器
chcp 65001 >nul
cd /d "%~dp0..\frontend"
if not exist node_modules (
    echo [init] 安装前端依赖（首次较慢）...
    call npm install
)
echo [run] 前端启动于 http://localhost:5173
call npm run dev
