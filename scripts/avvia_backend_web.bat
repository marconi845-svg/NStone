@echo off
REM Script principale per avviare il backend web completo
REM Usa percorsi relativi per essere portabile

REM Ottieni il percorso della directory dove si trova questo script
set "SCRIPT_DIR=%~dp0"
set "WEB_BACKEND_SCRIPT=%SCRIPT_DIR%web-backend\avvia_backend.bat"

REM Converti percorso in assoluto (necessario per verificare esistenza)
cd /d "%SCRIPT_DIR%"
set "SCRIPT_DIR=%CD%"
set "WEB_BACKEND_SCRIPT=%SCRIPT_DIR%\web-backend\avvia_backend.bat"

echo ========================================
echo Avvio Backend Web Completo
echo ========================================
echo.
echo Directory principale: %SCRIPT_DIR%
echo Script backend web: %WEB_BACKEND_SCRIPT%
echo.

REM Verifica che lo script esista
if not exist "%WEB_BACKEND_SCRIPT%" (
    echo ERRORE: Script backend web non trovato!
    echo Percorso atteso: %WEB_BACKEND_SCRIPT%
    echo.
    pause
    exit /b 1
)

REM Esegui lo script del backend web
call "%WEB_BACKEND_SCRIPT%"

REM Se lo script ha restituito un errore, propagalo
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ERRORE: Lo script backend web ha restituito un codice di errore.
    echo.
    pause
    exit /b %ERRORLEVEL%
)



