@echo off
setlocal
chcp 65001 >nul
title NEON//GRAB — by Badr Obtel
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo.
echo   NEON//GRAB  ·  crafted by Badr Obtel
echo.
echo   [*] first boot: building local runtime in .venv ...
where python >nul 2>nul || goto nopython
python -m venv .venv || goto fail
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --upgrade pip
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || goto fail
echo   [*] runtime ready.

:run
".venv\Scripts\python.exe" main.py
echo.
pause
exit /b

:nopython
echo   [!] Python was not found on PATH. Install it from https://www.python.org/ and re-run.
pause
exit /b 1

:fail
echo   [!] setup failed - see the messages above.
pause
exit /b 1
