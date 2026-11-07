@echo off
chcp 65001 >nul
title 四史学习助手 - 手机/平板访问
cd /d "%~dp0"

set CF=G:\wbdata\installs\cloudflared\cloudflared.exe
set LOG=G:\wbdata\installs\cloudflared\tunnel.log

echo.
echo  ==========================================================
echo    四史学习助手 - 手机 / 平板访问（可重复双击，不会重复启动）
echo  ==========================================================
echo.

if not exist "AILearningAssistant.exe" (
  echo  [X] 当前目录里没有 AILearningAssistant.exe
  pause
  exit /b 1
)

rem ---------- 服务：已在跑就跳过 ----------
tasklist /FI "IMAGENAME eq AILearningAssistant.exe" 2>nul | find /I "AILearningAssistant.exe" >nul
if not errorlevel 1 (
  echo  [1/2] 服务已在运行，跳过启动。
) else (
  if not exist "%CF%" (
    echo  [X] 找不到 cloudflared.exe：%CF%
    pause
    exit /b 1
  )
  echo  [1/2] 启动服务（0.0.0.0:8000）...
  start "四史学习助手-服务(别关)" AILearningAssistant.exe --lan
  set /a tries=0
  :waitapp
  timeout /t 2 /nobreak >nul
  curl -s -o nul --max-time 3 http://127.0.0.1:8000/api/health
  if not errorlevel 1 goto appok
  set /a tries+=1
  if %tries% lss 10 goto waitapp
  echo  [X] 服务没起来（可能被杀毒软件拦了，或 8000 被占用漂到 8001）
  pause
  exit /b 1
  :appok
  echo      服务就绪。
)

rem ---------- 隧道：已在跑就跳过 ----------
tasklist /FI "IMAGENAME eq cloudflared.exe" 2>nul | find /I "cloudflared.exe" >nul
if not errorlevel 1 (
  echo  [2/2] 公网隧道已在运行，跳过启动（地址不变）。
) else (
  echo  [2/2] 建立公网隧道（约 10 秒）...
  if exist "%LOG%" del "%LOG%" >nul 2>&1
  start "公网隧道(别关)" "%CF%" tunnel --url http://127.0.0.1:8000 --logfile "%LOG%"
  timeout /t 12 /nobreak >nul
)

echo.
echo  ------------------------------------------------------------
echo   同一 WiFi（家里/宿舍）:  http://本机IP:8000
echo     （软件左下角「手机访问」里有二维码）
echo.
echo   任何网络（流量 / 外面 WiFi）: 地址贴在「公网隧道(别关)」窗口，
echo   形如  https://xxxx-xxxx-xxx.trycloudflare.com
if exist "%LOG%" (
  echo.
  echo   日志里的地址记录（供查找）：
  findstr /C:".trycloudflare.com" "%LOG%"
)
echo.
echo   手机/平板浏览器打开后用「添加到主屏幕」当 App
echo   ！两个黑窗口都别关；关掉/重启电脑后地址会变，重新双击本脚本
echo  ------------------------------------------------------------
echo.
start "" http://127.0.0.1:8000
echo  按任意键关闭本提示窗口（服务继续在后台运行）
pause >nul
