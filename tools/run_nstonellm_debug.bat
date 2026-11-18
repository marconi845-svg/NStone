@echo off
title NSTONELLM DEBUG (log crash)
cd /d "%~dp0\.."
if not exist logs mkdir logs
echo Avvio con log su:
echo   logs\nstonellm_crash.log
echo   logs\session_debug.log
echo.
echo Dopo il crash apri quei file e cerca l'ultimo traceback.
echo.
python run.py >> logs\session_debug.log 2>&1
echo.
echo Exit code: %ERRORLEVEL%
echo Ultimi 40 righe del log sessione:
powershell -NoProfile -Command "Get-Content -Path 'logs\session_debug.log' -Tail 40"
pause
