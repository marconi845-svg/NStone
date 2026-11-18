@echo off
setlocal

REM ============================================================
REM Script portabile per avviare il PLC Virtuale Snap7 Lucidatrice
REM Funziona nella cartella della build NSTONELLM_App
REM ============================================================
title PLC Virtuale Snap7 - Lucidatrice/Calibratrice

REM Ottieni il percorso della directory dove si trova questo script
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
cd /d "%SCRIPT_DIR%"
set "SCRIPT_DIR=%CD%"

REM Se siamo in _internal, torna alla directory padre
echo %SCRIPT_DIR% | findstr /C:"\_internal" >nul
if not errorlevel 1 (
    cd /d "%SCRIPT_DIR%\.."
    set "SCRIPT_DIR=%CD%"
)

echo.
echo ============================================================
echo   PLC Virtuale Snap7 - Simulazione Lucidatrice/Calibratrice
echo ============================================================
echo.
echo Configurazione:
echo   - IP: 127.0.0.1
echo   - Porta: 102
echo   - Rack: 0, Slot: 1
echo.
echo Data Block simulati:
echo   - DB1: Stato macchina (7 byte)
echo   - DB2: Parametri macchina (44 byte = 11 Real)
echo   - DB3: Comandi macchina (3 byte)
echo.
echo NOTA: un solo simulatore alla volta puo' usare la porta 102.
echo ============================================================
echo.

REM Cerca l'eseguibile Snap7 server nella build (standalone, senza Python)
set "SERVER_EXE="

if exist "%SCRIPT_DIR%\snap7_lucidatrice_server.exe" (
    set "SERVER_EXE=%SCRIPT_DIR%\snap7_lucidatrice_server.exe"
) else (
    set "PARENT_DIR=%SCRIPT_DIR%\.."
    cd /d "%PARENT_DIR%"
    set "PARENT_DIR=%CD%"
    if exist "%PARENT_DIR%\snap7_lucidatrice_server.exe" (
        set "SERVER_EXE=%PARENT_DIR%\snap7_lucidatrice_server.exe"
        set "SCRIPT_DIR=%PARENT_DIR%"
    ) else (
        echo [ERRORE] Eseguibile snap7_lucidatrice_server.exe non trovato!
        echo.
        echo Cercato in:
        echo   - %SCRIPT_DIR%\snap7_lucidatrice_server.exe
        echo   - %PARENT_DIR%\snap7_lucidatrice_server.exe
        echo.
        pause
        exit /b 1
    )
)

echo Directory script: %SCRIPT_DIR%
echo Eseguibile server: %SERVER_EXE%
echo.
echo Per fermare il server, premi Ctrl+C o chiudi questa finestra.
echo ============================================================
echo.

"%SERVER_EXE%"

if errorlevel 1 (
    echo.
    echo ============================================================
    echo   [ERRORE] Il server Snap7 si e' chiuso con un errore
    echo ============================================================
    echo.
    echo Verifica:
    echo   1. Che la porta 102 non sia gia' in uso
    echo   2. Che non ci siano altri server Snap7 in esecuzione
    echo.
)

echo.
pause
