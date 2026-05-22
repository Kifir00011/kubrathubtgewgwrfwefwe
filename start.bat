@echo off
cd /d "%~dp0"
where cloudflared >nul 2>&1
if errorlevel 1 (
  echo cloudflared not found, installing via winget...
  winget install Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements
)
echo Installing Python deps...
python -m pip install -r requirements.txt -q
echo Starting File Tunnel + cloudflared...
python server.py
pause
