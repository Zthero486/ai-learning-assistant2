@echo off
chcp 65001 >nul
title 四史学习助手 - 手机/平板访问
cd /d "%~dp0"

set CF=G:\wbdata\installs\cloudflared\cloudflared.exe
set LOG=G:\wbdata\installs\cloudflared\tunnel.log

echo.
echo  ==========================================================
echo    四史学习助手 - 手机 / 平板访问
echo  ==========================================================
echo.

if not exist "AILearningAssistant.exe" (
  echo  [X] 当前目录里没有 AILearningAssistant.exe
  echo      请把本 bat 和 exe 放在同一个文件夹里运行。
  pause
  exit /b 1
)
if not exist "%CF%" (
  echo  [X] 找不到 cloudflared.exe：%CF%
  pause
  exit /b 1
)

echo  [1/2] 启动服务（0.0.0.0:8000，局域网可访问）...
start "四史学习助手-服务(别关)" AILearningAssistant.exe --lan

echo  [2/2] 等待服务就绪...
set /a tries=0
:waitapp
timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq AILearningAssistant.exe" 2>nul | find /I "AILearningAssistant.exe" >nul
if errorlevel 1 (
  set /a tries+=1
  if %tries% lss 8 goto waitapp
  echo  [X] 服务没有启动起来，请检查是否有杀毒软件拦截。
  pause
  exit /b 1
)

echo  服务已启动，正在建立公网隧道（约 10 秒）...
if exist "%LOG%" del "%LOG%" >nul 2>&1
start "公网隧道(别关)" "%CF%" tunnel --url http://127.0.0.1:8000 --logfile "%LOG%"

timeout /t 12 /nobreak >nul
echo.
echo  ------------------------------------------------------------
echo   同一 WiFi（家里/宿舍）:
echo      http://本机IP:8000      （软件左下角「手机访问」里有二维码）
echo.
echo   任何网络（用流量、在外面）:
echo      看「公网隧道(别关)」窗口里的  https://xxxx.trycloudflare.com
echo      也可以打开下面这个文件找到地址：
echo      %LOG%
echo.
echo   手机/平板浏览器打开后，用菜单「添加到主屏幕」当 App 用
echo   ！两个窗口都别关；这个临时地址在重启隧道后会变
echo  ------------------------------------------------------------
echo.
start "" http://127.0.0.1:8000
echo  按任意键关闭本提示窗口（服务继续在后台运行）
pause >nul
