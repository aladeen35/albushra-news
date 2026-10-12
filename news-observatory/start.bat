@echo off
rem Run Al-Bushra News on this computer (Windows): double-click start.bat
rem Needs Python 3.11 or newer from https://www.python.org/downloads/ (tick "Add to PATH").
chcp 65001 > nul
cd /d "%~dp0backend"

where python > nul 2>&1 || (echo Python 3 is required: https://www.python.org/downloads/ & pause & exit /b 1)

if not exist .venv (
  echo Installing requirements for the first time...
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\python -m pip install -q -r requirements.txt || (pause & exit /b 1)
)

if "%ADMIN_PASSWORD%"=="" set /p ADMIN_PASSWORD=Choose an admin password: 
if "%ADMIN_USERNAME%"=="" set ADMIN_USERNAME=admin
if "%DATABASE_URL%"=="" set DATABASE_URL=sqlite:///./data/albushra.db
set SCHEDULER_ENABLED=true
if "%SECRET_KEY%"=="" set SECRET_KEY=%RANDOM%%RANDOM%%RANDOM%%RANDOM%%RANDOM%%RANDOM%
if "%HDX_APP_NAME%"=="" set HDX_APP_NAME=albushra-news
if "%HDX_APP_EMAIL%"=="" set HDX_APP_EMAIL=albushra-news@users.noreply.github.com

echo.
echo   Site:   http://localhost:8000
echo   Admin:  http://localhost:8000/admin   (admin / your password)
echo   For a public link for your phone and the Android app, run in another window:
echo      cloudflared tunnel --url http://localhost:8000
echo.
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
