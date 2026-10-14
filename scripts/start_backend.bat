@echo off
REM 一键启动后端（首次运行自动创建虚拟环境并安装依赖）
chcp 65001 >nul
cd /d "%~dp0..\backend"
if not exist .venv (
    echo [init] 创建 Python 虚拟环境...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
echo [run] 后端启动于 http://127.0.0.1:8000
uvicorn app.main:app --port 8000
