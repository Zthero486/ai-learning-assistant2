@echo off
chcp 65001 >nul
title 四史学习助手 - 重启服务（隧道不动）
cd /d "%~dp0"

echo.
echo  重启服务：只换 exe 进程，公网隧道保持不动，地址不变
echo  ----------------------------------------------------------

if not exist "AILearningAssistant.exe" (
  echo  [X] 当前目录没有 AILearningAssistant.exe
  pause
  exit /b 1
)

echo  [1/3] 停止旧进程...
taskkill /F /IM AILearningAssistant.exe >nul 2>&1
:waitkill
timeout /t 1 /nobreak >nul
tasklist /FI "IMAGENAME eq AILearningAssistant.exe" 2>nul | find /I "AILearningAssistant.exe" >nul
if not errorlevel 1 goto waitkill

echo  [2/3] 启动新版本（--lan，端口 8000）...
start "四史学习助手-服务(别关)" AILearningAssistant.exe --lan

echo  [3/3] 等待服务就绪...
set /a tries=0
:waitready
timeout /t 2 /nobreak >nul
curl -s -o nul --max-time 3 http://127.0.0.1:8000/api/health
if not errorlevel 1 goto ready
set /a tries+=1
if %tries% lss 10 goto waitready
echo.
echo  [X] 8000 端口没有响应。常见原因：
echo      - 杀毒软件拦截了 exe
echo      - 8000 被其他程序占用，程序漂到了 8001（看新窗口里的地址）
echo      - 那就需要重开隧道：关闭「公网隧道」窗口，重新双击 手机访问-公网.bat
echo.
pause
exit /b 1

:ready
echo.
echo  ✅ 新版本已生效，手机端刷新页面即可（隧道没动，地址不变）
echo.
echo  当前公网地址：
findstr /C:"trycloudflare.com" "G:\wbdata\installs\cloudflared\tunnel.log" 2>nul | findstr /C:"https://" | findstr /V "api\." | find /V "Tunnel" | more +0
echo.
echo  （上面若没有显示，说明隧道没在跑；双击 手机访问-公网.bat 重开，地址会变）
echo.
if /I "%~1"=="auto" (
  echo  自动模式，5 秒后关闭本窗口
  timeout /t 5 >nul
  exit /b 0
)
pause
